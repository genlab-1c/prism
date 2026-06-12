"""Тесты слоя загрузчиков (harness/loaders.py).

Два среза:
1. Контракты реального репозитория — YAML в metrics/editions/generation/tasks
   валидны и согласованы между собой (это и есть «прехук» целостности данных).
2. Логика — compute_q и applicable_axes на синтетических случаях.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.loaders import (
    SCORER_TO_AXIS,
    Constitution,
    Edition,
    compute_q,
    load_constitution,
    load_edition,
    load_generation,
    load_protocol_l1,
    load_tasks,
)


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


def test_l1_bands_within_reachable(proto):
    """Каждая банда ведёт в достижимое значение своей оси."""
    for axis in proto.axes:
        assert set(proto.bands(axis)) <= set(proto.reachable(axis)), axis


def test_l1_o_weights_positive(proto):
    weights = proto.o_weights()
    assert weights, "белый список O пуст"
    assert all(w > 0 for w in weights.values())


def test_l1_o_unreachable_zero(proto):
    """Машина не ставит O=0 — это суждение Уровня 2 (см. протокол)."""
    assert 0 not in proto.reachable("O")


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


# ── compute_q (логика, синтетика) ────────────────────────────────────────────

@pytest.fixture()
def mini_const():
    """Минимальная конституция для изолированных проверок Q."""
    return Constitution(
        valid_scores=[0, 2, 4, 6, 8, 10],
        axes={
            "S": {"name": "С", "name_en": "S", "applies_to": ["A", "B"]},
            "M": {"name": "М", "name_en": "M", "applies_to": ["A", "B"]},
            "O": {"name": "О", "name_en": "O", "applies_to": ["A", "B"]},
            "P": {"name": "П", "name_en": "P", "applies_to": ["B"]},
        },
        q_formula="mean_of_applicable",
        q_primary_result="vector",
        thresholds={"high": 8, "acceptable": 5, "low": 0},
        version="t",
    )


def test_q_category_a_ignores_p(mini_const):
    """P не применима к A — не должна влиять на Q, даже если балл подан."""
    assert compute_q({"S": 10, "M": 8, "O": 6, "P": 0}, "A", mini_const) == 8.0


def test_q_category_b_includes_p(mini_const):
    assert compute_q({"S": 10, "M": 8, "O": 6, "P": 0}, "B", mini_const) == 6.0


def test_q_skips_unmeasured_axis(mini_const):
    """None = ось не измерена (нет инструмента) — исключается, не нулится."""
    assert compute_q({"S": 10, "M": None, "O": 6}, "A", mini_const) == 8.0


def test_q_no_measured_axes_is_none(mini_const):
    assert compute_q({"S": None, "M": None, "O": None}, "A", mini_const) is None


def test_q_unknown_formula_rejected(mini_const):
    broken = mini_const.model_copy(update={"q_formula": "weighted_sum"})
    with pytest.raises(AssertionError):
        compute_q({"S": 10, "M": 10, "O": 10}, "A", broken)


# ── валидация Pydantic ───────────────────────────────────────────────────────

def test_edition_missing_field_rejected():
    """Битый контракт издания падает на загрузке, а не глубоко в раннере."""
    with pytest.raises(ValidationError):
        Edition(name="x", mode="single-shot")      # нет context/scorers/leaderboard_view
