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
  prism score                                            # свежий прогон A и B, издание core
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

from rich.table import Table

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
    load_generation,
    load_protocol_l1,
    load_tasks,
)
from harness.score.meaning import band as m_band
from harness.score.meaning import fine_m, score_m
from harness.score.optimization import score_o
from harness.score.optimization_exec import score_o_exec
from harness.score.platform import score_p
from harness.score.quality import SCORER_TO_AXIS, compute_q
from harness.score.syntax import _cluster_lines, score_s
from harness.ui import brand_title, console, progress_bar


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
        return {
            "scores": scores,
            "bands": {"M": None, "P": None},
            "detail": {a: {"reason": f"генерация не удалась: {reason}"} for a in axes},
        }
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


def _onec_run_for(
    task: Task, code: str, work_dir: Path, instr: Instruments
) -> onec.OneCRunResult | None:
    """Исполнение кандидата B против синтетической базы — один раз на кандидата."""
    if instr.onec_run is None and onec.available():
        instr.onec_run = onec.run_candidate(
            code, task.dir, work_dir / "onec", task.entry_point_patterns
        )
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


def _score_meaning(
    task: Task, code: str, protocol: ProtocolL1, work_dir: Path, instr: Instruments
) -> tuple[float | None, dict]:
    if not task.testable:
        return None, {"reason": "нет скрытых тестов — ось M не исполнима"}
    if task.category == "B":  # исполнение в 1С (синтетическая база)
        if not onec.available():
            return None, {"reason": onec.unavailable_reason()}
        run = _onec_run_for(task, code, work_dir, instr)
        if run.status in ("infra_error", "no_result"):  # инфраструктура → «не измерено»
            return None, {
                "reason": f"исполнение не состоялось ({run.status})",
                "infra_detail": run.infra_detail[:300],
            }
        # no_entry / candidate_error — вина кандидата → floor 0 (как в кат. A)
        executed = run.status == "ok" and run.total > 0
        return (
            fine_m(run.passed, run.total, executed),
            {**run.model_dump(), "band": m_band(run.passed, run.total, executed, protocol)},
        )
    res = score_m(code, task.tests, protocol, work_dir, name="cand", runner=instr.runner)
    if res.score is None:  # ось не измерена (нет раннера)
        return None, res.model_dump(exclude={"score"})
    return (
        fine_m(res.passed, res.total, res.executed),
        {**res.model_dump(exclude={"score"}), "band": res.score},
    )


def _score_syntax(
    task: Task, code: str, protocol: ProtocolL1, work_dir: Path, instr: Instruments
) -> tuple[int | None, dict]:
    if task.category == "B":  # S(B) — компилятор 1С (/CheckModules)
        if not onec.available():
            return None, {"reason": onec.unavailable_reason()}
        run = _onec_run_for(task, code, work_dir, instr)
        if run.status in ("infra_error", "no_result"):
            return None, {"reason": f"исполнение не состоялось ({run.status})"}
        gap = protocol.axes["S"].cluster_gap or 3  # соседние ошибки = одна корневая причина
        clusters = _cluster_lines(sorted(run.compile_error_lines), gap)
        return protocol.scoring("S").score_for(clusters), {
            "root_causes": clusters,
            "instrument": "1С /CheckModules",
            "errors": run.compile_errors,
        }
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_s(instr.diagnostics, protocol, code)


def _score_optimization(
    task: Task, code: str, protocol: ProtocolL1, work_dir: Path, instr: Instruments
) -> tuple[int | None, dict]:
    # Категория A (есть perf.yaml): O мерится ТОЛЬКО исполнением (O-исп). Статический O-авто
    # в алгоритмике бесполезен (потолок 10), поэтому отката на него НЕТ: не измерилось → N/A.
    if task.perf is not None:
        if instr.runner is None or not instr.runner.available():
            return None, {"reason": "O-исп: раннер OneScript недоступен", "leg": "O-исп"}
        patterns = task.tests.entry_point_patterns if task.tests else []
        res = score_o_exec(
            code,
            task.perf,
            patterns,
            protocol,
            work_dir / "oexec",
            name="cand",
            runner=instr.runner,
        )
        # score=None (кандидат не исполнился / не нашли функцию) → N/A, не потолок O-авто
        return res.score, {**res.model_dump(exclude={"score"}), "leg": "O-исп"}
    # Задачи без perf (категория B): O-авто — статические perf/арх-антипаттерны BSL LS.
    if instr.diagnostics is None:
        return None, {"reason": f"BSL LS недоступен — {bsl_ls.unavailable_reason()}"}
    return score_o(instr.diagnostics, protocol)


def _score_platform(
    task: Task, code: str, protocol: ProtocolL1, work_dir: Path, instr: Instruments
) -> tuple[float | None, dict]:
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


SCORERS = {"S": _score_syntax, "M": _score_meaning, "O": _score_optimization, "P": _score_platform}

# Оси, чей инструмент — батч BSL LS (диагностики считаются один раз на прогон)
BSL_AXES = {"S", "O"}


# ── оценка одного кандидата ───────────────────────────────────────────────────


def score_candidate(
    task: Task,
    code: str,
    requested: set[str],
    constitution: Constitution,
    protocol: ProtocolL1,
    work_dir: Path,
    instr: Instruments,
) -> tuple[dict, dict]:
    """Все оси для одного кода → (scores {ось: балл|None, Q}, detail {ось: …}).

    scores[M], scores[P] — ПЛАВНЫЕ (доля × 10); scores[S], scores[O] — ступеньки.
    Q усредняет их как есть → лидерборд в полном разрешении. Ступеньки M/P для
    сверки с экспертом лежат в detail[ось]["band"] (поднимаются в run["bands"]).
    """
    applicable = set(constitution.applicable_axes(task.category))
    scores: dict[str, int | None] = {}
    detail: dict[str, dict] = {}
    for axis in constitution.axes:  # порядок S·M·O·P из конституции
        if axis not in applicable or axis not in requested:
            scores[axis] = None  # N/A для категории либо не просит издание
        elif axis not in SCORERS:
            scores[axis] = None
            detail[axis] = {"reason": "скорер оси не реализован"}
        else:
            scores[axis], detail[axis] = SCORERS[axis](task, code, protocol, work_dir, instr)
    scores["Q"] = compute_q(scores, task.category, constitution)
    return scores, detail


# ── прогон издания по эксперименту ────────────────────────────────────────────


def run(
    experiment_path: Path,
    edition_name: str,
    runner: Runner,
    model_ids: set[str] | None = None,
) -> dict:
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
        if model_ids is not None and tr["model_id"] not in model_ids:
            continue  # частичный скоринг: считаем только указанные модели
        task = tasks.get(tr["task_id"])
        if task is None:  # задача эксперимента не мигрирована в tasks/
            continue
        model_safe = tr["model_id"].replace("/", "_")
        for r in tr["runs"]:
            records.append(
                {
                    "tr": tr,
                    "r": r,
                    "task": task,
                    "code": extract_code(r["response"]),
                    "fname": f"{tr['task_id']}__{model_safe}__run{r['run_index']}.bsl",
                }
            )

    # Фаза 1: один батч BSL LS на всех кандидатов (старт JVM дорог) → {имя: диагностики}
    diags_by_file = _batch_diagnostics(records, requested, work_root)

    # Фаза 2: скоринг по осям. Кандидаты независимы → считаем параллельно (на баллы
    # не влияет: оценка из ответа модели, не из порядка/скорости). Результат собираем
    # в исходном порядке records, чтобы вывод оставался детерминированным.
    def _score_rec(rec: dict) -> dict:
        tr, r = rec["tr"], rec["r"]
        na = _failed_generation_run(r, constitution.axes)
        if na is not None:  # генерация прогона не удалась → N/A, не 0
            return {
                "key": (tr["task_id"], tr["model_id"]),
                "tr": tr,
                "run": {"run_index": r["run_index"], "response_hash": r.get("response_hash"), **na},
            }
        diags = None if diags_by_file is None else diags_by_file.get(rec["fname"], [])
        instr = Instruments(runner=runner, diagnostics=diags)
        work_dir = (
            work_root / tr["task_id"] / tr["model_id"].replace("/", "_") / f"run{r['run_index']}"
        )
        scores, detail = score_candidate(
            rec["task"], rec["code"], requested, constitution, protocol, work_dir, instr
        )
        return {
            "key": (tr["task_id"], tr["model_id"]),
            "tr": tr,
            "run": {
                "run_index": r["run_index"],
                "response_hash": r.get("response_hash"),
                "scores": scores,  # M/P плавные — лидерборд
                "bands": {
                    a: detail.get(a, {}).get("band") for a in ("M", "P")
                },  # ступеньки для сверки с экспертом (L2)
                "detail": detail,
            },
        }

    workers = _concurrency()
    with progress_bar("оценка кандидатов", len(records)) as advance:
        if workers > 1 and len(records) > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                scored = []
                for res in pool.map(_score_rec, records):  # map сохраняет порядок входа
                    scored.append(res)
                    advance()
        else:
            scored = []
            for rec in records:
                scored.append(_score_rec(rec))
                advance()

    groups: dict[tuple, dict] = {}
    for res in scored:  # сборка в порядке records
        tr = res["tr"]
        group = groups.setdefault(
            res["key"],
            {
                "task_id": tr["task_id"],
                "model_id": tr["model_id"],
                "model_name": tr["model_name"],
                "runs": [],
            },
        )
        group["runs"].append(res["run"])

    return {
        "experiment_id": exp_id,
        "evaluator_id": "auto_l1",  # против expert_01 в экспертной разметке
        "edition": edition.name,
        "leaderboard_view": edition.leaderboard_view,  # как ранжировать сводку (см. print_summary)
        "runner": runner.name,
        "syntax_analyzer": f"bsl-ls {bsl_ls.VERSION}" if diags_by_file is not None else None,
        "protocol_version": protocol.version,
        "constitution_version": constitution.version,
        "tasks": list(groups.values()),
    }


def _batch_diagnostics(
    records: list[dict], requested: set[str], work_root: Path
) -> dict[str, list[dict]] | None:
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
    table = Table(header_style="bold", row_styles=["", "dim"])
    table.add_column("задача")
    table.add_column("модель")
    for axis in ("S", "M", "O", "P"):
        table.add_column(axis, justify="right")
    table.add_column("Q", justify="right", style="bold")  # Q — итог, выделяем колонкой
    if expert:
        for col in ("S·эксп", "M·эксп", "Q·эксп"):
            table.add_column(col, justify="right")
        table.add_column("M-детали")
    for t in result["tasks"]:
        model = t["model_name"][:16]
        for r in t["runs"]:
            s = r["scores"]
            row = [
                t["task_id"],
                model,
                _fmt(s["S"]),
                _fmt(s["M"]),
                _fmt(s["O"]),
                _fmt(s["P"]),
                _fmt(s["Q"]),
            ]
            if expert:
                e = expert.get((t["task_id"], t["model_id"], r["run_index"]), {})
                md = r["detail"].get("M", {})
                m_info = (
                    f"{md.get('passed', '')}/{md.get('total', '')}"
                    if md.get("total")
                    else md.get("reason", "")
                )
                row += [_fmt(e.get("S")), _fmt(e.get("M")), _fmt(e.get("Q")), m_info]
            table.add_row(*row)
    console.print(table)


def print_leaderboard(result: dict) -> None:
    """Ранжирование моделей по Q̄ + средние по осям S·M·O·P (по модели).

    n — число оценённых прогонов (где Q измерена). Средние берутся по измеренным
    значениям оси (None — «не измерено» — в среднее не входит; нет ни одного → «—»).
    """
    axes = ("S", "M", "O", "P", "Q")
    by_model: dict[str, dict[str, list[float]]] = {}
    for t in result["tasks"]:
        for r in t["runs"]:
            s = r["scores"]
            if s.get("Q") is None:
                continue
            bucket = by_model.setdefault(t["model_name"], {a: [] for a in axes})
            for a in axes:
                if s.get(a) is not None:
                    bucket[a].append(s[a])
    if not by_model:
        return

    def avg(vals: list[float], prec: int = 1) -> str:
        return f"{sum(vals) / len(vals):.{prec}f}" if vals else "—"

    table = Table(
        title="Лидерборд — средние баллы по моделям",
        title_style="bold",
        header_style="bold",
    )
    table.add_column("#", justify="right")
    table.add_column("модель")
    for col in ("S̄", "M̄", "Ō", "P̄"):
        table.add_column(col, justify="right")
    table.add_column("Q̄", justify="right", style="bold")  # ключ ранжирования
    table.add_column("n", justify="right")
    ranked = sorted(
        by_model.items(),
        key=lambda kv: sum(kv[1]["Q"]) / len(kv[1]["Q"]) if kv[1]["Q"] else -1.0,
        reverse=True,
    )
    for i, (name, b) in enumerate(ranked, 1):
        table.add_row(
            str(i),
            name,
            avg(b["S"]),
            avg(b["M"]),
            avg(b["O"]),
            avg(b["P"]),
            avg(b["Q"], 2),
            str(len(b["Q"])),
        )
    console.print(table)


# ── прогон + отчёт (зовётся из CLI: prism score) ──────────────────────────────


def _is_mock_experiment(path: Path) -> bool:
    """Сухой прогон конвейера (модель mock/echo) — не настоящий эксперимент для оценки.

    Иначе оставшийся после `generate --mock` файл стал бы «свежим» для категории и
    засорял бы авто-выбор `score`/`leaderboard`."""
    try:
        used = json.loads(path.read_text(encoding="utf-8")).get("models_used") or []
    except (OSError, json.JSONDecodeError):
        return False
    return bool(used) and all(str(m).lower().startswith("mock") for m in used)


def _is_mock_auto(path: Path) -> bool:
    """Не-настоящая авто-оценка L1: mock-прогон (model_id == mock/echo) ИЛИ пустая (0 задач).

    Пустые auto появляются, когда оценивать нечего (напр. `score --models X` против прогона
    без модели X) — на лидерборд их пускать нельзя."""
    try:
        tasks = json.loads(path.read_text(encoding="utf-8")).get("tasks") or []
    except (OSError, json.JSONDecodeError):
        return False
    ids = {str(t.get("model_id", "")) for t in tasks}
    return not ids or all(i.lower().startswith("mock") for i in ids)


def _prefer_real(runs: list[Path], is_mock) -> list[Path]:
    """Отсеять mock; но если настоящих нет — вернуть всё (демо `--mock` без реальных прогонов)."""
    real = [r for r in runs if not is_mock(r)]
    return real or runs


def newest_experiment(category: str = "A") -> Path:
    """Свежайший НАСТОЯЩИЙ experiment_<cat>_*.json (mock игнорируется, если есть реальные)."""
    runs = sorted((PRISM / "results").glob(f"experiment_{category}_*.json"))
    if not runs:
        raise SystemExit(f"в results/ нет experiment_{category}_*.json")
    return _prefer_real(runs, _is_mock_experiment)[-1]


def newest_experiments() -> dict[str, Path]:
    """{категория: свежайший НАСТОЯЩИЙ experiment_<cat>_*.json} по всем категориям.

    Основа дефолта `prism score` без аргументов: оценить свежий прогон И A, И B, а не
    только A. Mock-прогоны (`generate --mock`) пропускаются, пока есть реальные — иначе
    забытый сухой прогон становился бы «свежим» и оценивался вместо настоящего."""
    found: dict[str, Path] = {}
    for cat in ("A", "B"):
        runs = sorted((PRISM / "results").glob(f"experiment_{cat}_*.json"))
        if runs:
            found[cat] = _prefer_real(runs, _is_mock_experiment)[-1]
    return found


def newest_auto(category: str | None = None) -> Path:
    """Последняя по времени НАСТОЯЩАЯ авто-оценка L1 из results/auto/ (mock игнорируется).

    category=None — across A/B (для `prism submit`); иначе только указанной категории."""
    pattern = f"experiment_{category}_*_auto_l1.json" if category else "*_auto_l1.json"
    runs = _prefer_real(list((PRISM / "results" / "auto").glob(pattern)), _is_mock_auto)
    if not runs:
        where = f" категории {category}" if category else ""
        raise SystemExit(f"в results/auto/ нет оценок L1{where} — сначала запустите `prism score`")
    return max(runs, key=lambda p: p.stat().st_mtime)


def newest_autos() -> list[Path]:
    """Свежайший НАСТОЯЩИЙ auto_l1 каждой категории (A раньше B) — для лидерборда A+B."""
    out: list[Path] = []
    for cat in ("A", "B"):
        runs = list((PRISM / "results" / "auto").glob(f"experiment_{cat}_*_auto_l1.json"))
        runs = _prefer_real(runs, _is_mock_auto)
        if runs:
            out.append(max(runs, key=lambda p: p.stat().st_mtime))
    return out


def print_report(result: dict, experiment_path: Path, full: bool = False) -> None:
    """Сводка по готовому L1-результату: лидерборд (всегда) + детали по --full.

    По умолчанию — только компактный лидерборд (быстро глянуть, кто впереди). full —
    добавить построчную таблицу S·M·O·P·Q (+сверка с экспертом) и срезы по тегам.
    Издание без quality-лидерборда (ранжировать нечем) → сразу детальная таблица.
    """
    is_quality = result.get("leaderboard_view") == "quality"
    if is_quality:
        print_leaderboard(result)
    if full or not is_quality:
        if is_quality:
            console.print()
        print_summary(result, experiment_path)
        console.print()
        print_funnel(result)
        console.print()
        print_tag_profiles(result)


def _print_one_leaderboard(auto_path: Path, full: bool) -> None:
    result = json.loads(auto_path.read_text(encoding="utf-8"))
    # эксперимент рядом с auto (для сверки с экспертом в --full); может и не существовать
    experiment_path = PRISM / "results" / f"{result['experiment_id']}.json"
    console.print(f"  [dim]· {auto_path.name}[/dim]\n", highlight=False)
    print_report(result, experiment_path, full=full)


def leaderboard_report(auto_path: Path | None = None, full: bool = False) -> list[Path]:
    """Мгновенная сводка из СОХРАНЁННОЙ авто-оценки L1 — без пере-исполнения в 1С.

    Без явного пути печатает свежайший лидерборд КАЖДОЙ категории (A и B, как в README),
    а не одну случайную по mtime."""
    brand_title("лидерборд")
    if auto_path is not None:
        _print_one_leaderboard(auto_path, full)
        return [auto_path]
    paths = newest_autos()
    if not paths:
        raise SystemExit("в results/auto/ нет оценок L1 — сначала запустите `prism score`")
    for i, p in enumerate(paths):
        if i:
            console.print()
        _print_one_leaderboard(p, full)
    return paths


def score_report(
    experiment_path: Path,
    edition_name: str = "core",
    out_path: Path | None = None,
    full: bool = False,
    model_keys: list[str] | None = None,
) -> Path:
    """Прогнать издание по эксперименту (пересчёт в 1С), записать L1 и напечатать сводку.

    model_keys — оценить только эти модели (ключи каталога): результат ДОЗАПИСЫВАЕТСЯ в
    существующий auto_l1 (прежние модели берутся готовыми, не пересчитываются). Так
    добавляют новые генерации, не гоняя 1С по уже посчитанному базлайну.
    """
    brand_title("оценка L1")
    runner = get_runner()
    if not runner.available():
        console.print(
            f"  [yellow]●[/yellow] раннер {runner.name} недоступен: {runner.unavailable_reason()}",
            highlight=False,
        )
        console.print(
            "    ось M выйдет «не измерена» (score=None) для всех кандидатов.", style="dim"
        )

    model_ids = None
    if model_keys:  # ключи каталога → id моделей (run/auto_l1 оперируют id)
        catalog = load_generation().models
        model_ids = {catalog[k].id for k in model_keys if k in catalog}
        unknown = [k for k in model_keys if k not in catalog]
        if unknown:
            console.print(
                f"  [yellow]●[/yellow] нет в каталоге, пропущены: {', '.join(unknown)}",
                highlight=False,
            )
        if not model_ids:
            raise SystemExit("ни одной известной модели в --models")

    result = run(experiment_path, edition_name, runner, model_ids=model_ids)

    out_path = out_path or (PRISM / "results" / "auto" / f"{result['experiment_id']}_auto_l1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if model_ids is not None and out_path.exists():  # дозапись: сохранить прежние модели
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        kept = [g for g in prev.get("tasks", []) if g["model_id"] not in model_ids]
        result["tasks"] = kept + result["tasks"]
        console.print(
            f"дозапись в {out_path.name}: пересчитано моделей {len(model_ids)}, "
            f"сохранено прежних групп {len(kept)}\n",
            style="dim",
            highlight=False,
        )

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    analyzer = result["syntax_analyzer"] or "S/O вне издания или анализатор недоступен"
    console.print(
        f"  [dim]издание {result['edition']} × {experiment_path.name}[/dim]\n"
        f"  [dim]раннер {result['runner']} · синтаксис {analyzer} · "
        f"протокол L1 v{result['protocol_version']}[/dim]\n",
        highlight=False,
    )
    print_report(result, experiment_path, full=full)
    console.print(f"\n→ {out_path.relative_to(PRISM)}", style="green", highlight=False)
    console.print(
        "  детали по прогонам: --full · переоткрыть без пересчёта: prism leaderboard",
        style="dim",
        highlight=False,
    )
    return out_path


# Исходы воронки от лучшего к худшему. Цвет + символ-градиент (█▓▒░): полоса читается
# и в монохроме (solid = хорошо, бледный = плохо), цвет не несёт смысл в одиночку.
_FUNNEL_STYLE = {
    "решено": ("green", "█"),
    "неверный ответ": ("yellow", "▓"),
    "ошибка выполнения": ("dark_orange3", "▒"),
    "не компилируется": ("red", "░"),
}
_FUNNEL_BAR_WIDTH = 20


def _funnel_bar(buckets: dict, n: int) -> str:
    """Полоса-отсев: доли исходов символами █▓▒░ в цвете, в сумме на всю ширину.

    Наибольшие остатки добивают ширину ровно до W, ненулевая корзина не схлопывается
    в ноль (иначе редкий, но реальный исход исчезал бы)."""
    from harness.stats.funnel import BUCKETS

    raw = {b: buckets[b] / n * _FUNNEL_BAR_WIDTH for b in BUCKETS}
    widths = {b: int(raw[b]) for b in BUCKETS}
    widths = {b: (1 if widths[b] == 0 and buckets[b] else widths[b]) for b in BUCKETS}
    short = _FUNNEL_BAR_WIDTH - sum(widths.values())
    for b in sorted(BUCKETS, key=lambda b: raw[b] - int(raw[b]), reverse=True):
        if short <= 0:
            break
        widths[b] += 1
        short -= 1
    return "".join(
        f"[{_FUNNEL_STYLE[b][0]}]{_FUNNEL_STYLE[b][1] * widths[b]}[/]" for b in BUCKETS if widths[b]
    )


def print_funnel(result: dict) -> None:
    """Где ломается код у каждой модели — все попытки по итогу (а не сколько баллов).

    Полоса = все попытки, поделённые на 4 итога: решено / неверный ответ (код отработал,
    но результат не тот) / ошибка выполнения (упал при запуске или работе) / не
    компилируется. В сумме всегда 100%. «самая частая поломка» — что чинить первым.
    Атрибуция к корню: итог считается там, где прогон ВПЕРВЫЕ сломался, без двойного счёта.
    """
    from harness.loaders import load_error_taxonomy
    from harness.stats.funnel import funnel

    rows = funnel(result, load_error_taxonomy())
    if not rows:
        return
    legend = "   ".join(f"[{c}]{g}[/] {b}" for b, (c, g) in _FUNNEL_STYLE.items())
    console.print("где ломается код у каждой модели (все попытки = 100%)", style="bold")
    console.print(f"  {legend}", highlight=False)
    table = Table(header_style="bold", title_justify="left")
    table.add_column("модель", no_wrap=True)
    table.add_column("решено", justify="right", style="bold green")  # ключевое число — вперёд
    table.add_column("результат попыток", width=_FUNNEL_BAR_WIDTH, no_wrap=True)
    table.add_column("самая частая поломка")  # последняя — может переноситься без вреда
    table.add_column("n", justify="right")

    for name, f in rows:
        cause = f["cause"]
        cause_txt = f"{cause[0]} ×{cause[1]}" if cause else "—"
        table.add_row(
            name,
            f"{round(f['solved'] * 100)}%",
            _funnel_bar(f["buckets"], f["n"]),
            cause_txt,
            str(f["n"]),
        )
    console.print(table)


def print_tag_profiles(result: dict) -> None:
    """Срезы качества по тегам — по каждой модели (где модель сильнее/слабее)."""
    from harness.stats.tags import tag_profile

    tasks_by_id = {t.id: t for t in load_tasks()}
    by_model: dict[tuple, list] = {}
    for t in result["tasks"]:
        by_model.setdefault((t["model_id"], t["model_name"]), []).append(t)
    console.print(
        "── срезы по тегам (M̄ — логика, P̄ — платформа; n — задач; модель-vs-модель) ──",
        style="bold",
        highlight=False,
    )
    for (_mid, mname), groups in by_model.items():
        prof = tag_profile(groups, tasks_by_id)
        if not prof:
            continue
        table = Table(  # одна таблица на модель; измерения разделены секциями
            title=f"профиль по тегам — {mname}",
            title_style="bold",
            title_justify="left",
            header_style="bold",
        )
        table.add_column("измерение")
        table.add_column("тег")
        table.add_column("M̄", justify="right")
        table.add_column("P̄", justify="right")
        table.add_column("n", justify="right")
        for di, dim in enumerate(sorted(prof)):
            if di:
                table.add_section()
            rows = sorted(prof[dim].items(), key=lambda kv: (-(kv[1].get("M") or -1), kv[0]))
            for ti, (tag, row) in enumerate(rows):
                m = "—" if row.get("M") is None else f"{row['M']:.1f}"
                p = "—" if row.get("P") is None else f"{row['P']:.1f}"
                low = row["n"] < 3  # тег на 1–2 задачах — шум; гасим строку и метим ⚠
                table.add_row(
                    dim if ti == 0 else "",
                    tag,
                    m,
                    p,
                    f"{row['n']} ⚠" if low else str(row["n"]),
                    style="dim" if low else None,
                )
        console.print(table)
