"""Тесты оркестратора L1 (harness/orchestrate.py).

Без OneScript: проверяется СВЯЗКА оркестратора, не сами скореры (их интеграция —
в test_meaning.py). Скорер M подменяется фейком, чтобы детерминированно проверить
гейтинг осей (N/A для категории, нереализованные, не запрошенные изданием) и
агрегацию Q поверх измеренного.
"""

from __future__ import annotations

import pytest

from harness import orchestrate
from harness.loaders import Task, load_constitution, load_protocol_l1


@pytest.fixture(scope="module")
def const():
    return load_constitution()


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


def make_task(tmp_path, category="A", tests=None) -> Task:
    return Task(
        id="T1",
        name="проба",
        category=category,
        difficulty="easy",
        entry_point="Ф",
        signature="Ф()",
        prompt="…",
        dir=tmp_path,
        tests=tests,
    )


ALL_AXES = {"S", "M", "O", "P"}
NO_INSTRUMENTS = orchestrate.Instruments(runner=None, diagnostics=None)


# ── извлечение кода из ответа модели ─────────────────────────────────────────


def test_extract_fenced_1c():
    assert (
        orchestrate.extract_code("```1c\nФункция Ф()\nКонецФункции\n```")
        == "Функция Ф()\nКонецФункции"
    )


def test_extract_prose_around_fence():
    """Заборы среди текста: берём первый блок, обрамление отбрасываем."""
    resp = "Вот решение:\n```bsl\nКОД\n```\nГотово."
    assert orchestrate.extract_code(resp) == "КОД"


def test_extract_no_fence_returns_stripped():
    assert orchestrate.extract_code("  просто код  ") == "просто код"


# ── гейтинг осей и агрегация Q ───────────────────────────────────────────────


def test_non_testable_task_m_not_measured(const, proto, tmp_path):
    """Нет скрытых тестов → M=None (не ноль), Q=None (нечего усреднять)."""
    task = make_task(tmp_path, category="A", tests=None)
    scores, detail = orchestrate.score_candidate(
        task, "код", ALL_AXES, const, proto, tmp_path, NO_INSTRUMENTS
    )
    assert scores["M"] is None
    assert "нет скрытых тестов" in detail["M"]["reason"]
    assert scores["P"] is None  # P неприменима к A
    assert scores["S"] is None and detail["S"]["reason"]  # нет диагностик BSL LS → не измерена
    assert scores["Q"] is None


def test_q_aggregates_only_measured(const, proto, tmp_path, monkeypatch):
    """M подставлен фейком → Q = среднее по применимым измеренным (только M)."""
    monkeypatch.setitem(orchestrate.SCORERS, "M", lambda *a: (10, {"ok": True}))
    task = make_task(tmp_path, category="A")
    scores, _ = orchestrate.score_candidate(
        task, "x", ALL_AXES, const, proto, tmp_path, NO_INSTRUMENTS
    )
    assert scores["M"] == 10
    assert scores["S"] is None and scores["O"] is None  # пока не реализованы
    assert scores["P"] is None  # N/A для A
    assert scores["Q"] == 10.0


def test_fine_score_flows_to_continuous_q(const, proto, tmp_path, monkeypatch):
    """M плавный (8.0) проходит в scores как есть и даёт непрерывный Q — без округления."""
    monkeypatch.setitem(orchestrate.SCORERS, "M", lambda *a: (8.0, {"band": 6}))
    task = make_task(tmp_path, category="A")
    scores, detail = orchestrate.score_candidate(
        task, "x", ALL_AXES, const, proto, tmp_path, NO_INSTRUMENTS
    )
    assert scores["M"] == 8.0  # плавная оценка, не ступенька
    assert detail["M"]["band"] == 6  # ступенька сохранена для сверки с L2
    assert scores["Q"] == 8.0  # Q по единственной измеренной оси M


def test_unrequested_axis_skipped(const, proto, tmp_path, monkeypatch):
    """Издание не просит M → ось не считается, даже если скорер есть."""
    monkeypatch.setitem(orchestrate.SCORERS, "M", lambda *a: (10, {}))
    task = make_task(tmp_path, category="A")
    scores, _ = orchestrate.score_candidate(
        task, "x", {"S", "O", "P"}, const, proto, tmp_path, NO_INSTRUMENTS
    )
    assert scores["M"] is None
    assert scores["Q"] is None


# ── провал генерации (success=False) → N/A, а не 0 ───────────────────────────


def test_failed_generation_is_na_not_zero(const):
    """Упавший вызов (напр. 404) не должен скориться как «модель выдала плохой код»."""
    r = {"success": False, "error": "HTTP 404: unknown model", "run_index": 0}
    na = orchestrate._failed_generation_run(r, const.axes)
    assert na is not None
    assert all(na["scores"][a] is None for a in const.axes)  # все оси «не измерено»
    assert na["scores"]["Q"] is None
    assert "404" in na["detail"]["M"]["reason"]


def test_successful_or_legacy_run_scored_normally(const):
    assert orchestrate._failed_generation_run({"success": True}, const.axes) is None
    assert orchestrate._failed_generation_run({}, const.axes) is None  # легаси без поля — оцениваем


# ── выбор свежих прогонов/оценок: A и B, а не только A ────────────────────────


def _touch(p, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    if mtime is not None:
        import os

        os.utime(p, (mtime, mtime))


def test_newest_experiments_covers_both_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrate, "PRISM", tmp_path)
    res = tmp_path / "results"
    _touch(res / "experiment_A_20260101_000000.json")
    _touch(res / "experiment_A_20260102_000000.json")  # свежее по имени
    _touch(res / "experiment_B_20260101_000000.json")
    found = orchestrate.newest_experiments()
    assert set(found) == {"A", "B"}  # B больше не выпадает
    assert found["A"].name == "experiment_A_20260102_000000.json"  # свежайший A


def test_newest_autos_one_per_category(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrate, "PRISM", tmp_path)
    auto = tmp_path / "results" / "auto"
    _touch(auto / "experiment_A_20260101_000000_auto_l1.json", mtime=1000)
    _touch(auto / "experiment_A_20260102_000000_auto_l1.json", mtime=2000)  # новее по mtime
    _touch(auto / "experiment_B_20260101_000000_auto_l1.json", mtime=1500)
    autos = orchestrate.newest_autos()
    names = sorted(p.name for p in autos)
    assert names == [
        "experiment_A_20260102_000000_auto_l1.json",
        "experiment_B_20260101_000000_auto_l1.json",
    ]
    # category-фильтр newest_auto берёт только свою категорию
    assert orchestrate.newest_auto("B").name == "experiment_B_20260101_000000_auto_l1.json"
