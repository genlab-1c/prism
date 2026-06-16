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

Запуск (CLI prism, см. cli.py):
  prism score                                            # свежайший experiment_A_*.json, издание core
  prism score --experiment results/experiment_B_20260301_130327.json
  PRISM_RUNNER=docker prism score                        # ось M кат. A в песочнице
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from harness.execute import bsl_ls
from harness.execute.onec import runner as onec
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
from harness.score.meaning import band as m_band
from harness.score.meaning import fine_m, score_m
from harness.score.optimization import score_o
from harness.score.platform import score_p
from harness.score.quality import SCORER_TO_AXIS, compute_q
from harness.score.syntax import _cluster_lines, score_s


def _concurrency() -> int:
    """Сколько кандидатов считать параллельно (env PRISM_CONCURRENCY; по умолчанию ≤4).

    На БАЛЛЫ не влияет — только на скорость: кандидаты независимы (свой work_dir,
    контейнер B изолирован --network=none). Память: B-прогон поднимает 1С-клиент,
    поэтому при нехватке RAM снизьте число — нехватка проявится как «не измерено»
    (None), а НЕ как неверный балл.
    """
    env = os.environ.get("PRISM_CONCURRENCY")
    if env and env.isdigit() and int(env) > 0:
        return int(env)
    return min(4, os.cpu_count() or 1)


def _failed_generation_run(r: dict, axes) -> dict | None:
    """Прогон с провалившейся генерацией (success=False) → N/A по всем осям, а НЕ 0.

    Сетевой/доступовый сбой (например 404 «unknown model») не должен топить балл модели,
    будто она «выдала плохой код»: это «не измерено». Прогоны без поля success (легаси)
    считаем валидными → возврат None (оцениваем как обычно).
    """
    if r.get("success") is False:
        reason = (r.get("error") or "генерация не удалась")[:200]
        scores: dict = {a: None for a in axes}
        scores["Q"] = None
        return {"scores": scores, "bands": {"M": None, "P": None},
                "detail": {a: {"reason": f"генерация не удалась: {reason}"} for a in axes}}
    return None

FENCE_RE = re.compile(r"```(?:[\wа-яА-Я+]+)?\s*\n(.*?)```", re.DOTALL)


@dataclass
class Instruments:
    """Контекст инструментов для скореров одного кандидата.

    runner — раннер OneScript (ось M кат. A). diagnostics — диагностики BSL LS
    этого кандидата для осей S/O (None = анализатор недоступен → ось «не
    измерена»; [] = файл чист). onec_run — кэш результата исполнения в 1С для
    категории B: ОДИН прогон, из него и M (passed/total), и P (платформенные
    ошибки). Каждый скорер берёт из контекста только нужное ему.
    """

    runner: Runner | None = None
    diagnostics: list[dict] | None = None
    onec_run: onec.OneCRunResult | None = None


def _onec_run_for(task: Task, code: str, work_dir: Path,
                  instr: Instruments) -> onec.OneCRunResult | None:
    """Исполнение кандидата B против синтетической базы — один раз на кандидата."""
    if instr.onec_run is None and onec.available():
        instr.onec_run = onec.run_candidate(
            code, task.dir, work_dir / "onec", task.entry_point_patterns)
    return instr.onec_run


# ── извлечение кода кандидата ─────────────────────────────────────────────────

def extract_code(response: str) -> str:
    """Код из ответа модели: первый ```-блок, иначе весь текст как есть."""
    m = FENCE_RE.search(response)
    return (m.group(1) if m else response).strip()


# ── реестр скореров: ось → как её посчитать ──────────────────────────────────
#
# Контракт: (task, code, protocol, work_dir, instr) → (score|None, detail).
# None = ось не измерена (нет инструмента/тестов). Сюда подключаются O/P.
# Для M и P score — ПЛАВНЫЙ (доля × 10, лидербордный); ступенька (дискретная ступень
# шкалы 0..10) для сверки с экспертом кладётся в detail["band"] и поднимается в
# run["bands"] (см. score_candidate).

def _score_meaning(task: Task, code: str, protocol: ProtocolL1,
                   work_dir: Path, instr: Instruments) -> tuple[float | None, dict]:
    if not task.testable:
        return None, {"reason": "нет скрытых тестов — ось M не исполнима"}
    if task.category == "B":                        # исполнение в 1С (синтетическая база)
        if not onec.available():
            return None, {"reason": onec.unavailable_reason()}
        run = _onec_run_for(task, code, work_dir, instr)
        if run.status in ("infra_error", "no_result"):    # инфраструктура → «не измерено»
            return None, {"reason": f"исполнение не состоялось ({run.status})",
                          "infra_detail": run.infra_detail[:300]}
        # no_entry / candidate_error — вина кандидата → floor 0 (как в кат. A)
        executed = run.status == "ok" and run.total > 0
        return (fine_m(run.passed, run.total, executed),
                {**run.model_dump(), "band": m_band(run.passed, run.total, executed, protocol)})
    res = score_m(code, task.tests, protocol, work_dir, name="cand", runner=instr.runner)
    if res.score is None:                           # ось не измерена (нет раннера)
        return None, res.model_dump(exclude={"score"})
    return (fine_m(res.passed, res.total, res.executed),
            {**res.model_dump(exclude={"score"}), "band": res.score})


def _score_syntax(task: Task, code: str, protocol: ProtocolL1,
                  work_dir: Path, instr: Instruments) -> tuple[int | None, dict]:
    if task.category == "B":                        # S(B) — компилятор 1С (/CheckModules)
        if not onec.available():
            return None, {"reason": onec.unavailable_reason()}
        run = _onec_run_for(task, code, work_dir, instr)
        if run.status in ("infra_error", "no_result"):
            return None, {"reason": f"исполнение не состоялось ({run.status})"}
        gap = protocol.axes["S"].cluster_gap or 3   # соседние ошибки = одна корневая причина
        clusters = _cluster_lines(sorted(run.compile_error_lines), gap)
        return protocol.scoring("S").score_for(clusters), {
            "root_causes": clusters, "instrument": "1С /CheckModules",
            "errors": run.compile_errors}
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_s(instr.diagnostics, protocol, code)


def _score_optimization(task: Task, code: str, protocol: ProtocolL1,
                        work_dir: Path, instr: Instruments) -> tuple[int | None, dict]:
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_o(instr.diagnostics, protocol)


def _score_platform(task: Task, code: str, protocol: ProtocolL1,
                    work_dir: Path, instr: Instruments) -> tuple[float | None, dict]:
    """P из ТОГО ЖЕ прогона 1С, что и M (кэш instr.onec_run): один запуск, два сигнала.

    Возвращает ПЛАВНУЮ оценку (чистая доля × 10) для лидерборда; ступенька score_p
    (для сверки с экспертом) кладётся в detail["band"].
    """
    if not task.testable:
        return None, {"reason": "нет комплекта исполнения — ось P не исполнима"}
    if not onec.available():
        return None, {"reason": onec.unavailable_reason()}
    run = _onec_run_for(task, code, work_dir, instr)
    band, detail = score_p(run, protocol)
    if band is None:
        return None, detail
    share = detail.get("clean_share")
    fine = round(share * 10, 1) if share is not None else float(band)
    return fine, {**detail, "band": band}


SCORERS = {"S": _score_syntax, "M": _score_meaning,
           "O": _score_optimization, "P": _score_platform}

# Оси, чей инструмент — батч BSL LS (диагностики считаются один раз на прогон)
BSL_AXES = {"S", "O"}


# ── оценка одного кандидата ───────────────────────────────────────────────────

def score_candidate(task: Task, code: str, requested: set[str],
                    constitution: Constitution, protocol: ProtocolL1,
                    work_dir: Path, instr: Instruments) -> tuple[dict, dict]:
    """Все оси для одного кода → (scores {ось: балл|None, Q}, detail {ось: …}).

    scores[M], scores[P] — ПЛАВНЫЕ (доля × 10); scores[S], scores[O] — ступеньки.
    Q усредняет их как есть → лидерборд в полном разрешении. Ступеньки M/P для
    сверки с экспертом лежат в detail[ось]["band"] (поднимаются в run["bands"]).
    """
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

    # Фаза 2: скоринг по осям. Кандидаты независимы → считаем параллельно (на баллы
    # не влияет: оценка из ответа модели, не из порядка/скорости). Результат собираем
    # в исходном порядке records, чтобы вывод оставался детерминированным.
    def _score_rec(rec: dict) -> dict:
        tr, r = rec["tr"], rec["r"]
        na = _failed_generation_run(r, constitution.axes)
        if na is not None:                          # генерация прогона не удалась → N/A, не 0
            return {"key": (tr["task_id"], tr["model_id"]), "tr": tr,
                    "run": {"run_index": r["run_index"],
                            "response_hash": r.get("response_hash"), **na}}
        diags = None if diags_by_file is None else diags_by_file.get(rec["fname"], [])
        instr = Instruments(runner=runner, diagnostics=diags)
        work_dir = work_root / tr["task_id"] / tr["model_id"].replace("/", "_") / f"run{r['run_index']}"
        scores, detail = score_candidate(
            rec["task"], rec["code"], requested, constitution, protocol, work_dir, instr)
        return {
            "key": (tr["task_id"], tr["model_id"]), "tr": tr,
            "run": {
                "run_index": r["run_index"],
                "response_hash": r.get("response_hash"),
                "scores": scores,                       # M/P плавные — лидерборд
                "bands": {a: detail.get(a, {}).get("band") for a in ("M", "P")},  # ступеньки для сверки с экспертом (L2)
                "detail": detail,
            },
        }

    workers = _concurrency()
    if workers > 1 and len(records) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            scored = list(pool.map(_score_rec, records))    # map сохраняет порядок входа
    else:
        scored = [_score_rec(rec) for rec in records]

    groups: dict[tuple, dict] = {}
    for res in scored:                                       # сборка в порядке records
        tr = res["tr"]
        group = groups.setdefault(res["key"], {
            "task_id": tr["task_id"], "model_id": tr["model_id"],
            "model_name": tr["model_name"], "runs": []})
        group["runs"].append(res["run"])

    return {
        "experiment_id": exp_id,
        "evaluator_id": "auto_l1",                  # против expert_01 в экспертной разметке
        "edition": edition.name,
        "leaderboard_view": edition.leaderboard_view,   # как ранжировать сводку (см. print_summary)
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
    head = f"{'задача':<6} {'модель':<16} {'S':>3} {'M':>5} {'O':>3} {'P':>5} {'Q':>5}"
    if expert:
        head += f"   {'S·эксп':>6} {'M·эксп':>6} {'Q·эксп':>6}  M-детали"
    print(head)
    print("─" * len(head))
    for t in result["tasks"]:
        model = t["model_name"][:16]
        for r in t["runs"]:
            s = r["scores"]
            line = (f"{t['task_id']:<6} {model:<16} "
                    f"{_fmt(s['S']):>3} {_fmt(s['M']):>5} {_fmt(s['O']):>3} "
                    f"{_fmt(s['P']):>5} {_fmt(s['Q']):>5}")
            if expert:
                e = expert.get((t["task_id"], t["model_id"], r["run_index"]), {})
                md = r["detail"].get("M", {})
                m_info = (f"{md.get('passed', '')}/{md.get('total', '')}"
                          if md.get("total") else md.get("reason", ""))
                line += (f"   {_fmt(e.get('S')):>6} {_fmt(e.get('M')):>6} "
                         f"{_fmt(e.get('Q')):>6}  {m_info}")
            print(line)

    if result.get("leaderboard_view") == "quality":
        print_leaderboard(result)


def print_leaderboard(result: dict) -> None:
    """Ранжирование моделей по среднему Q (издание.leaderboard_view = quality)."""
    by_model: dict[str, list[float]] = {}
    for t in result["tasks"]:
        for r in t["runs"]:
            q = r["scores"].get("Q")
            if q is not None:
                by_model.setdefault(t["model_name"], []).append(q)
    if not by_model:
        return
    print("\nЛидерборд (средний Q):")
    ranked = sorted(((sum(v) / len(v), name) for name, v in by_model.items()), reverse=True)
    for i, (avg, name) in enumerate(ranked, 1):
        print(f"  {i}. {name:<18} Q̄ = {avg:.2f}  (n={len(by_model[name])})")


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
    print()
    print_tag_profiles(result)
    print(f"\n→ {out_path.relative_to(PRISM)}")
    return out_path


def print_tag_profiles(result: dict) -> None:
    """Срезы качества по тегам — по каждой модели (где модель сильнее/слабее)."""
    from harness.stats.tags import format_tag_profile, tag_profile

    tasks_by_id = {t.id: t for t in load_tasks()}
    by_model: dict[tuple, list] = {}
    for t in result["tasks"]:
        by_model.setdefault((t["model_id"], t["model_name"]), []).append(t)
    print("── срезы по тегам (M̄ — логика, P̄ — платформа; n — задач; модель-vs-модель) ──")
    for (_mid, mname), groups in by_model.items():
        prof = tag_profile(groups, tasks_by_id)
        if prof:
            print(format_tag_profile(mname, prof))
