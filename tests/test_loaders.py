"""Тесты слоя загрузчиков (harness/loaders.py).

Два среза:
1. Контракты реального репозитория — YAML в metrics/editions/generation/tasks
   валидны и согласованы между собой (это и есть «прехук» целостности данных).
2. Логика — applicable_axes (метод модели) на синтетических случаях.

Агрегация Q вынесена в слой скоринга — её тесты в test_quality.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.loaders import (
    Edition,
    load_constitution,
    load_edition,
    load_generation,
    load_protocol_l1,
    load_tasks,
)
from harness.score.quality import SCORER_TO_AXIS


# ── фикстуры: грузим реальные контракты один раз ─────────────────────────────

@pytest.fixture(scope="module")
def const():
    return load_constitution()


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


@pytest.fixture(scope="module")
def tasks():
    return load_tasks()


# ── конституция ──────────────────────────────────────────────────────────────

def test_constitution_axes(const):
    assert list(const.axes) == ["S", "M", "O", "P"]


def test_constitution_scale(const):
    assert const.valid_scores == [0, 2, 4, 6, 8, 10]


def test_constitution_q_rule(const):
    assert const.q_formula == "mean_of_applicable"
    assert const.q_primary_result == "vector"


def test_applicable_axes_category_a_excludes_p(const):
    assert const.applicable_axes("A") == ["S", "M", "O"]


def test_applicable_axes_category_b_all(const):
    assert const.applicable_axes("B") == ["S", "M", "O", "P"]


# ── протокол L1 ──────────────────────────────────────────────────────────────

def test_l1_axes_match_constitution(const, proto):
    """Протокол не выдумывает осей сверх конституции."""
    assert set(proto.axes) == set(const.axes)


def test_l1_reachable_subset_of_scale(const, proto):
    """Достижимые значения каждой оси — подмножество общей шкалы."""
    for axis in proto.axes:
        assert set(proto.reachable(axis)) <= set(const.valid_scores), axis


def test_l1_scoring_scores_in_scale(const, proto):
    """Каждый балл в scoring.table — из общей шкалы."""
    for axis in proto.axes:
        assert {r.score for r in proto.scoring(axis).table} <= set(const.valid_scores), axis


def test_l1_direction_valid(proto):
    for axis in proto.axes:
        assert proto.scoring(axis).direction in {"lower_is_better", "higher_is_better"}, axis


def test_l1_o_weights_positive(proto):
    weights = proto.o_weights()
    assert weights, "white_list O пуст"
    assert all(w > 0 for w in weights.values())


def test_l1_o_unreachable_zero(proto):
    """Машина не ставит O=0 — это суждение Уровня 2 (см. протокол)."""
    assert 0 not in proto.reachable("O")


# ── единый движок score_for (обе оси направления) ────────────────────────────

def test_score_for_lower_is_better(proto):
    """S: меньше причин → выше балл; else-строка для >6."""
    s = proto.scoring("S")
    assert [s.score_for(n) for n in (0, 1, 2, 3, 6, 7)] == [10, 8, 6, 6, 4, 2]


def test_score_for_higher_is_better(proto):
    """M: больше доля → выше балл; exclusive >0 и хвостовой else=0."""
    m = proto.scoring("M")
    assert [m.score_for(x) for x in (1.0, 0.9, 0.6, 0.5)] == [10, 8, 6, 4]
    assert m.score_for(0.001) == 2          # > 0% (exclusive)
    assert m.score_for(0.0) == 0            # else: 0% / не исполнился


# ── задачи ───────────────────────────────────────────────────────────────────

def test_tasks_loaded(tasks):
    assert [t.id for t in tasks] == ["A1", "A2", "A3", "A4", "A5"]


def test_tasks_category_filter():
    assert all(t.category == "A" for t in load_tasks(category="A"))
    assert load_tasks(category="B") == []          # B пока не мигрирована


def test_tasks_a1_a4_testable(tasks):
    """У A1–A4 есть скрытые тесты; ось M исполнима."""
    for t in tasks:
        if t.id in {"A1", "A2", "A3", "A4"}:
            assert t.testable, t.id
            assert t.tests.entry_point_patterns, f"{t.id}: нет паттернов entry point"


def test_tasks_a5_pending(tasks):
    a5 = next(t for t in tasks if t.id == "A5")
    assert not a5.testable
    assert a5.m_testing == "pending_harness"


def test_tasks_a1_has_canonical(tasks):
    a1 = next(t for t in tasks if t.id == "A1")
    assert a1.canonical is not None and a1.canonical.exists()


# ── издание и генерация ──────────────────────────────────────────────────────

def test_edition_core():
    core = load_edition("core")
    assert core.mode == "single-shot"
    assert core.context == "mcp"
    assert set(core.scorers) <= set(SCORER_TO_AXIS), "неизвестный скорер в издании"


def test_generation_catalog():
    gen = load_generation()
    assert set(gen.models) == {"claude", "gpt", "gemini"}
    for key, m in gen.models.items():
        assert m.access.adapter == "openrouter", key
    assert "A" in gen.prompts


def test_generation_params_cover_models():
    """Числовые параметры заданы для каждой модели каталога."""
    gen = load_generation()
    assert set(gen.params["model_params"]) == set(gen.models)


# ── валидация Pydantic ───────────────────────────────────────────────────────

def test_edition_missing_field_rejected():
    """Битый контракт издания падает на загрузке, а не глубоко в раннере."""
    with pytest.raises(ValidationError):
        Edition(name="x", mode="single-shot")      # нет context/scorers/leaderboard_view
