"""Оркестратор L1: издание × готовые генерации → авто-оценка (оси × Q) → results/auto/.

Связывает слои в один прогон, без новой генерации:
  experiment_*.json (выходы моделей) → детект кода кандидата → скореры осей
  → compute_q → запись в схеме, ЗЕРКАЛЬНОЙ экспертной разметке (results/evaluations/),
  чтобы авто и эксперт были diff-абельны рукой и машиной.

Оси без реализованного скорера (S/O/P пока) и неприменимые к категории → score=None
(«не измерено»), а не ноль — compute_q штатно исключает их из среднего. Реестр
SCORERS — единственное место, куда подключается новая ось.

Если рядом лежит экспертный файл (results/evaluations/<exp>_expert_*.json), сводка
печатает дельту авто↔эксперт по M и Q — первая проверка согласованности.

Запуск:
  python3 -m harness.orchestrate                       # свежайший experiment_A_*.json, издание core
  python3 -m harness.orchestrate --experiment results/experiment_A_20260301_125458.json
  PRISM_RUNNER=docker python3 -m harness.orchestrate   # скоринг в песочнице
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from harness.execute import bsl_ls
from harness.execute.runner import Runner, get_runner
from harness.loaders import (
    PRISM,
    Constitution,
    ProtocolL1,
    Task,
    load_constitution,
    load_edition,
    load_protocol_l1,
    load_tasks,
)
from harness.score.meaning import score_m
from harness.score.optimization import score_o
from harness.score.quality import SCORER_TO_AXIS, compute_q
from harness.score.syntax import score_s

FENCE_RE = re.compile(r"```(?:[\wа-яА-Я+]+)?\s*\n(.*?)```", re.DOTALL)


@dataclass
class Instruments:
    """Контекст инструментов для скореров одного кандидата.

    runner — раннер OneScript (ось M). diagnostics — диагностики BSL LS этого
    кандидата для осей S/O (None = анализатор недоступен → ось «не измерена»;
    [] = файл чист). Каждый скорер берёт из контекста только нужное ему.
    """

    runner: Runner | None = None
    diagnostics: list[dict] | None = None


# ── извлечение кода кандидата ─────────────────────────────────────────────────

def extract_code(response: str) -> str:
    """Код из ответа модели: первый ```-блок, иначе весь текст как есть."""
    m = FENCE_RE.search(response)
    return (m.group(1) if m else response).strip()


# ── реестр скореров: ось → как её посчитать ──────────────────────────────────
#
# Контракт: (task, code, protocol, work_dir, instr) → (score|None, detail).
# None = ось не измерена (нет инструмента/тестов). Сюда подключаются O/P.

def _score_meaning(task: Task, code: str, protocol: ProtocolL1,
                   work_dir: Path, instr: Instruments) -> tuple[int | None, dict]:
    if not task.testable:
        return None, {"reason": "нет скрытых тестов — ось M не исполнима"}
    res = score_m(code, task.tests, protocol, work_dir, name="cand", runner=instr.runner)
    return res.score, res.model_dump(exclude={"score"})


def _score_syntax(task: Task, code: str, protocol: ProtocolL1,
                  work_dir: Path, instr: Instruments) -> tuple[int | None, dict]:
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_s(instr.diagnostics, protocol, code)


def _score_optimization(task: Task, code: str, protocol: ProtocolL1,
                        work_dir: Path, instr: Instruments) -> tuple[int | None, dict]:
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_o(instr.diagnostics, protocol)


SCORERS = {"S": _score_syntax, "M": _score_meaning, "O": _score_optimization}   # P — Уровень 2 для B

# Оси, чей инструмент — батч BSL LS (диагностики считаются один раз на прогон)
BSL_AXES = {"S", "O"}


# ── оценка одного кандидата ───────────────────────────────────────────────────

def score_candidate(task: Task, code: str, requested: set[str],
                    constitution: Constitution, protocol: ProtocolL1,
                    work_dir: Path, instr: Instruments) -> tuple[dict, dict]:
    """Все оси для одного кода → (scores {ось: балл|None, Q}, detail {ось: …})."""
    applicable = set(constitution.applicable_axes(task.category))
    scores: dict[str, int | None] = {}
    detail: dict[str, dict] = {}
    for axis in constitution.axes:                  # порядок S·M·O·P из конституции
        if axis not in applicable or axis not in requested:
            scores[axis] = None                     # N/A для категории либо не просит издание
        elif axis not in SCORERS:
            scores[axis] = None
            detail[axis] = {"reason": "скорер оси не реализован"}
        else:
            scores[axis], detail[axis] = SCORERS[axis](task, code, protocol, work_dir, instr)
    scores["Q"] = compute_q(scores, task.category, constitution)
    return scores, detail


# ── прогон издания по эксперименту ────────────────────────────────────────────

def run(experiment_path: Path, edition_name: str, runner: Runner) -> dict:
    constitution = load_constitution()
    protocol = load_protocol_l1()
    edition = load_edition(edition_name)
    tasks = {t.id: t for t in load_tasks()}
    requested = {SCORER_TO_AXIS[s] for s in edition.scorers if s in SCORER_TO_AXIS}

    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    exp_id = experiment["experiment_name"]
    work_root = PRISM / "work" / exp_id

    # Кандидаты в порядке эксперимента; уникальное имя файла → ключ диагностик BSL LS
    records = []
    for tr in experiment["task_results"]:
        task = tasks.get(tr["task_id"])
        if task is None:                            # задача эксперимента не мигрирована в tasks/
            continue
        model_safe = tr["model_id"].replace("/", "_")
        for r in tr["runs"]:
            records.append({
                "tr": tr, "r": r, "task": task,
                "code": extract_code(r["response"]),
                "fname": f"{tr['task_id']}__{model_safe}__run{r['run_index']}.bsl",
            })

    # Фаза 1: один батч BSL LS на всех кандидатов (старт JVM дорог) → {имя: диагностики}
    diags_by_file = _batch_diagnostics(records, requested, work_root)

    # Фаза 2: скоринг по осям, группировка по (задача, модель) как в экспертной схеме
    groups: dict[tuple, dict] = {}
    for rec in records:
        tr, r = rec["tr"], rec["r"]
        diags = None if diags_by_file is None else diags_by_file.get(rec["fname"], [])
        instr = Instruments(runner=runner, diagnostics=diags)
        work_dir = work_root / tr["task_id"] / tr["model_id"].replace("/", "_") / f"run{r['run_index']}"
        scores, detail = score_candidate(
            rec["task"], rec["code"], requested, constitution, protocol, work_dir, instr)
        key = (tr["task_id"], tr["model_id"])
        group = groups.setdefault(key, {
            "task_id": tr["task_id"], "model_id": tr["model_id"],
            "model_name": tr["model_name"], "runs": []})
        group["runs"].append({
            "run_index": r["run_index"],
            "response_hash": r.get("response_hash"),
            "scores": scores,
            "detail": detail,
        })

    return {
        "experiment_id": exp_id,
        "evaluator_id": "auto_l1",                  # против expert_01 в экспертной разметке
        "edition": edition.name,
        "runner": runner.name,
        "syntax_analyzer": f"bsl-ls {bsl_ls.VERSION}" if diags_by_file is not None else None,
        "protocol_version": protocol.version,
        "constitution_version": constitution.version,
        "tasks": list(groups.values()),
    }


def _batch_diagnostics(records: list[dict], requested: set[str],
                       work_root: Path) -> dict[str, list[dict]] | None:
    """Один прогон BSL LS на всех кандидатов → {имя_файла: диагностики}.

    None — анализатор не нужен (издание не просит S/O) либо недоступен: оси S/O
    выйдут «не измерены». Иначе пишем плоскую src/ и анализируем разом.
    """
    if not (requested & BSL_AXES) or not bsl_ls.available():
        return None
    src = work_root / "_bslls" / "src"
    src.mkdir(parents=True, exist_ok=True)
    for rec in records:
        (src / rec["fname"]).write_text(rec["code"], encoding="utf-8")
    return bsl_ls.analyze(src, work_root / "_bslls" / "out")


# ── сводка и сверка с экспертом ───────────────────────────────────────────────

def _expert_index(experiment_path: Path) -> dict[tuple, dict]:
    """{(task_id, model_id, run_index): scores} из экспертного файла, если он есть."""
    exp_dir = experiment_path.parent / "evaluations"
    matches = sorted(exp_dir.glob(f"{experiment_path.stem}_expert_*.json"))
    if not matches:
        return {}
    doc = json.loads(matches[0].read_text(encoding="utf-8"))
    idx = {}
    for t in doc["tasks"]:
        for r in t["runs"]:
            idx[(t["task_id"], t["model_id"], r["run_index"])] = r["scores"]
    return idx


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def print_summary(result: dict, experiment_path: Path) -> None:
    expert = _expert_index(experiment_path)
    head = f"{'задача':<6} {'модель':<16} {'S':>3} {'M':>3} {'O':>3} {'P':>3} {'Q':>5}"
    if expert:
        head += f"   {'S·эксп':>6} {'M·эксп':>6} {'Q·эксп':>6}  M-детали"
    print(head)
    print("─" * len(head))
    for t in result["tasks"]:
        model = t["model_name"][:16]
        for r in t["runs"]:
            s = r["scores"]
            line = (f"{t['task_id']:<6} {model:<16} "
                    f"{_fmt(s['S']):>3} {_fmt(s['M']):>3} {_fmt(s['O']):>3} "
                    f"{_fmt(s['P']):>3} {_fmt(s['Q']):>5}")
            if expert:
                e = expert.get((t["task_id"], t["model_id"], r["run_index"]), {})
                md = r["detail"].get("M", {})
                m_info = (f"{md.get('passed', '')}/{md.get('total', '')}"
                          if md.get("total") else md.get("reason", ""))
                line += (f"   {_fmt(e.get('S')):>6} {_fmt(e.get('M')):>6} "
                         f"{_fmt(e.get('Q')):>6}  {m_info}")
            print(line)


# ── прогон + отчёт (зовётся из CLI: prism score) ──────────────────────────────

def newest_experiment() -> Path:
    """Свежайший experiment_A_*.json из results/ (по сортировке имени = по дате)."""
    runs = sorted((PRISM / "results").glob("experiment_A_*.json"))
    if not runs:
        raise SystemExit("в results/ нет experiment_A_*.json")
    return runs[-1]


def score_report(experiment_path: Path, edition_name: str = "core",
                 out_path: Path | None = None) -> Path:
    """Прогнать издание по эксперименту, записать результат, напечатать сводку."""
    runner = get_runner()
    if not runner.available():
        print(f"⚠ раннер {runner.name} недоступен: {runner.unavailable_reason()}")
        print("  ось M выйдет «не измерена» (score=None) для всех кандидатов.")

    result = run(experiment_path, edition_name, runner)

    out_path = out_path or (PRISM / "results" / "auto"
                            / f"{result['experiment_id']}_auto_l1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    analyzer = result["syntax_analyzer"] or "S/O вне издания или анализатор недоступен"
    print(f"издание {result['edition']} × {experiment_path.name}\n"
          f"раннер {result['runner']} · синтаксис {analyzer} · протокол L1 v{result['protocol_version']}\n")
    print_summary(result, experiment_path)
    print(f"\n→ {out_path.relative_to(PRISM)}")
    return out_path
