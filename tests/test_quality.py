"""Тесты слоя скоринга: агрегация Q (harness/score/quality.py).

compute_q на синтетических конституциях — изолированно от реальных YAML.
Контракты реальной конституции проверяет test_loaders.py.
"""

from __future__ import annotations

import pytest

from harness.loaders import Constitution
from harness.score.quality import compute_q, coverage


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


# ── охват осей: без него Q двух записей несравним ────────────────────────────


def test_coverage_counts_only_applicable_axes(mini_const):
    """P не применима к A, поэтому знаменатель охвата там три, а не четыре."""
    assert coverage({"S": 10, "M": 8, "O": 6, "P": 0}, "A", mini_const) == (3, 3)
    assert coverage({"S": 10, "M": 8, "O": 6, "P": 0}, "B", mini_const) == (4, 4)


def test_coverage_shows_what_q_hides(mini_const):
    """Неизмеренная ось ПОДНИМАЕТ Q, и охват — единственное, что об этом сообщает.

    Несобравшийся модуль (S=8 за одну корневую причину, M=0, O и P не измерены) даёт
    Q=4.0 — выше, чем полная запись с Q=3.0. Сравнивать их по одному Q нельзя.
    """
    broken = {"S": 8, "M": 0, "O": None, "P": None}
    assert compute_q(broken, "B", mini_const) == 4.0
    assert coverage(broken, "B", mini_const) == (2, 4)

    full = {"S": 10, "M": 2, "O": 0, "P": 0}
    assert compute_q(full, "B", mini_const) == 3.0
    assert coverage(full, "B", mini_const) == (4, 4)


def test_coverage_zero_when_nothing_measured(mini_const):
    assert coverage({"S": None, "M": None, "O": None, "P": None}, "B", mini_const) == (0, 4)
