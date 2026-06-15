"""Проверка целостности бенчмарка (prism check): контракты + задания + эталоны.

Три уровня, от дешёвого к дорогому:
 1. Контракты метрики — конституция/протокол/издания/генерация грузятся и
    согласованы между собой (оси, шкала, банды, веса, белый список скореров).
 2. Контракты заданий — каждая задача валидна; у исполнимых есть тесты и паттерны
    entry point; задачи без тестов помечаются (pending), это не ошибка.
 3. Когерентность эталонов — самый сильный инвариант: canonical.bsl каждой задачи
    ПРОХОДИТ свои же скрытые тесты на 100%. Разом валидирует и тесты, и эталон.
    Требует OneScript; нет инструмента → срез пропускается (skip), не падает.

Плюс срез доступности инструментов по осям (oscript / BSL LS+java).

run_checks() возвращает (секции, ok). ok=False, если есть хоть один FAIL
(нарушенный контракт или эталон, не прошедший свои тесты). Печать — в cli.py.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from harness.execute import bsl_ls
from harness.execute.onec import runner as onec
from harness.execute.runner import get_runner
from harness.loaders import (
    PRISM,
    load_constitution,
    load_edition,
    load_generation,
    load_protocol_l1,
    load_tags_vocab,
    load_tasks,
)
from harness.score.meaning import score_m
from harness.score.optimization import score_o
from harness.score.quality import SCORER_TO_AXIS
from harness.score.syntax import score_s

# Статусы пунктов: ok — норма; warn — деградация (не ошибка); fail — нарушение; skip — не проверяли
Item = tuple[str, str]            # (status, text)
Section = dict                    # {"title": str, "items": list[Item]}


def run_checks() -> tuple[list[Section], bool]:
    sections = [
        _check_contracts(),
        _check_tasks(),
        _check_canonicals(),
        _check_instruments(),
    ]
    ok = not any(st == "fail" for s in sections for st, _ in s["items"])
    return sections, ok


# ── 1. контракты метрики ─────────────────────────────────────────────────────

def _check_contracts() -> Section:
    items: list[Item] = []
    try:
        const = load_constitution()
        proto = load_protocol_l1()
        gen = load_generation()
    except Exception as e:                                  # noqa: BLE001 — показываем как fail
        return {"title": "Контракты метрики", "items": [("fail", f"загрузка: {e}")]}

    items.append(("ok", f"конституция v{const.version}: оси {list(const.axes)}, "
                        f"шкала {const.valid_scores}"))

    if set(proto.axes) == set(const.axes):
        items.append(("ok", f"протокол L1 v{proto.version}: оси совпадают с конституцией"))
    else:
        items.append(("fail", f"оси протокола {set(proto.axes)} ≠ конституции {set(const.axes)}"))

    for axis in proto.axes:
        scoring = proto.scoring(axis)
        if not {r.score for r in scoring.table} <= set(const.valid_scores):
            items.append(("fail", f"ось {axis}: балл в scoring.table вне шкалы"))
        if scoring.direction not in {"lower_is_better", "higher_is_better"}:
            items.append(("fail", f"ось {axis}: неизвестное direction {scoring.direction!r}"))
        if not set(proto.reachable(axis)) <= set(const.valid_scores):
            items.append(("fail", f"ось {axis}: достижимые баллы вне шкалы"))
    weights = proto.o_weights()
    if weights and all(w > 0 for w in weights.values()):
        items.append(("ok", f"ось O: white_list ({len(weights)} кодов), все веса > 0"))
    else:
        items.append(("fail", "ось O: пустой или неположительный white_list"))

    # издания: их скореры — из известных
    for path in sorted((PRISM / "editions").glob("*.yaml")):
        ed = load_edition(path.stem)
        unknown = set(ed.scorers) - set(SCORER_TO_AXIS)
        if unknown:
            items.append(("fail", f"издание {ed.name}: неизвестные скореры {unknown}"))
        else:
            items.append(("ok", f"издание {ed.name}: scorers {ed.scorers} ✓"))

    # генерация: числовые параметры покрывают каталог моделей
    if set(gen.params.get("model_params", {})) == set(gen.models):
        items.append(("ok", f"генерация: параметры покрывают все {len(gen.models)} моделей"))
    else:
        items.append(("fail", "генерация: params не покрывают каталог моделей"))
    return {"title": "Контракты метрики", "items": items}


# ── 2. контракты заданий ─────────────────────────────────────────────────────

def _check_tasks() -> Section:
    items: list[Item] = []
    try:
        tasks = load_tasks()
        vocab = load_tags_vocab()
    except Exception as e:                                  # noqa: BLE001
        return {"title": "Контракты заданий", "items": [("fail", f"загрузка задач/тегов: {e}")]}

    items.append(("ok", f"загружено задач: {len(tasks)} ({', '.join(t.id for t in tasks)})"))
    items.append(("ok", f"словарь тегов v{vocab.version}: измерения {list(vocab.dimensions)}"))
    untagged = [t.id for t in tasks if not t.tags]
    if untagged:
        items.append(("warn", f"без тегов (нет срезов анализа): {', '.join(untagged)}"))
    for t in tasks:
        if t.category not in {"A", "B"}:
            items.append(("fail", f"{t.id}: недопустимая категория {t.category!r}"))
        tag_errors = vocab.validate_task_tags(t.tags, t.category)
        for err in tag_errors:
            items.append(("fail", f"{t.id}: теги — {err}"))
        if t.category == "B":
            items.extend(_check_task_b(t))
            continue
        if not (t.entry_point and t.signature and t.prompt):
            items.append(("fail", f"{t.id}: пустое обязательное поле (entry_point/signature/prompt)"))
        if t.testable:
            if not t.tests.entry_point_patterns:
                items.append(("fail", f"{t.id}: есть тесты, но нет entry_point_patterns"))
            bad = [i for i, c in enumerate(t.tests.tests) if "args" not in c or "expected" not in c]
            if bad:
                items.append(("fail", f"{t.id}: кейсы без args/expected: {bad}"))
            else:
                items.append(("ok", f"{t.id}: {len(t.tests.tests)} тест-кейсов, паттерны заданы"))
        else:
            reason = f" ({t.m_testing})" if t.m_testing else ""
            items.append(("warn", f"{t.id}: без скрытых тестов — ось M не исполнима{reason}"))
    return {"title": "Контракты заданий", "items": items}


def _check_task_b(t) -> list[Item]:
    """Контракт B-задачи: prompt + паттерны + полный комплект исполнения."""
    items: list[Item] = []
    if not (t.prompt and t.entry_point_patterns):
        items.append(("fail", f"{t.id}: пустое обязательное поле (prompt/entry_point_patterns)"))
    missing = [f for f in ("config_spec.yaml", "fixtures.yaml", "tests.bsl")
               if not (t.dir / f).exists()]
    if missing:
        items.append(("warn", f"{t.id}: нет {', '.join(missing)} — исполнение B не собрано"))
    else:
        items.append(("ok", f"{t.id}: комплект B (спека базы, фикстуры, проверки) на месте"))
    return items


# ── 3. когерентность эталонов (эталон проходит свои тесты) ────────────────────

def _check_canonicals() -> Section:
    proto = load_protocol_l1()
    tasks = [t for t in load_tasks() if t.canonical and t.testable]
    tasks_a = [t for t in tasks if t.category == "A"]
    tasks_b = [t for t in tasks if t.category == "B"]
    runner = get_runner()

    items: list[Item] = []
    work = Path(tempfile.mkdtemp(prefix="prism_check_"))

    # — категория A: OneScript
    if not runner.available():
        items.append(("skip", f"кат. A: пропуск (M — гейт): {runner.unavailable_reason()}"))
        tasks_a = []
    diags = _canonical_diagnostics(tasks_a, work)  # S/O — батч BSL LS, {id: [диагностики]} или None
    for t in tasks_a:
        code = t.canonical.read_text(encoding="utf-8")
        # M — ЖЁСТКИЙ гейт: эталон обязан пройти свои тесты на 100%
        m = score_m(code, t.tests, proto, work / t.id, name=f"canon_{t.id}", runner=runner)
        gate = m.executed and m.passed == m.total and m.score == 10
        m_txt = (f"M=10 ({m.passed}/{m.total})" if gate
                 else f"M={m.score} ({m.passed}/{m.total}) — {m.errors[:1]}")
        # S/O — пока только показываем, не гейтим (эталон ожидаем образцовым)
        if diags is None:
            so_txt = "S/O: BSL LS недоступен"
        else:
            s, _ = score_s(diags.get(t.id, []), proto, code)
            o, _ = score_o(diags.get(t.id, []), proto)
            so_txt = f"S={s} · O={o}"
        items.append(("ok" if gate else "fail", f"{t.id}: эталон {m_txt} · {so_txt}"))

    # — категория B: исполнение против синтетической базы (тот же жёсткий гейт)
    if tasks_b and not onec.available():
        items.append(("skip", f"кат. B: пропуск (M/P — гейт): {onec.unavailable_reason()}"))
        tasks_b = []
    for t in tasks_b:
        code = t.canonical.read_text(encoding="utf-8-sig")
        run = onec.run_candidate(code, t.dir, work / t.id, t.entry_point_patterns)
        gate = (run.status == "ok" and run.total > 0 and run.passed == run.total
                and not run.platform_errors and not run.compile_error_lines)
        txt = (f"S=10 · M=10 ({run.passed}/{run.total}) · P чисто" if gate
               else f"{run.status}: {run.passed}/{run.total}"
                    f"{' · компиляция: ' + str(run.compile_errors[:1]) if run.compile_error_lines else ''}"
                    f"{' · платформенные ошибки: ' + str(run.platform_errors) if run.platform_errors else ''}"
                    f"{' · ' + (run.log or run.infra_detail)[:120] if not gate else ''}")
        items.append(("ok" if gate else "fail", f"{t.id}: эталон (1С) {txt}"))

    if not items:
        items.append(("warn", "нет задач с эталоном и тестами для проверки"))
    return {"title": "Когерентность эталонов", "items": items}


def _canonical_diagnostics(tasks, work: Path) -> dict | None:
    """Один батч BSL LS по всем эталонам → {id: диагностики}. None — анализатор недоступен."""
    if not bsl_ls.available():
        return None
    src = work / "_bslls" / "src"
    src.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        (src / f"{t.id}.bsl").write_text(t.canonical.read_text(encoding="utf-8"), encoding="utf-8")
    report = bsl_ls.analyze(src, work / "_bslls" / "out")
    return {t.id: report.get(f"{t.id}.bsl", []) for t in tasks}


# ── 4. доступность инструментов по осям ──────────────────────────────────────

def _check_instruments() -> Section:
    items: list[Item] = []
    runner = get_runner()
    if runner.available():
        items.append(("ok", f"M (meaning): раннер {runner.name} ✓"))
    else:
        items.append(("warn", f"M (meaning): {runner.unavailable_reason()} — ось не измеряется"))
    if bsl_ls.available():
        items.append(("ok", f"S/O (syntax/optimization): {bsl_ls.describe()} ✓"))
    else:
        items.append(("warn", f"S/O: {bsl_ls.unavailable_reason()} — оси не измеряются"))
    if onec.available():
        items.append(("ok", f"S/M/P кат. B (1С): docker-образ {onec.DOCKER_IMAGE} ✓"))
    else:
        items.append(("warn", f"M/P кат. B: {onec.unavailable_reason()}"))
    return {"title": "Инструменты по осям", "items": items}
