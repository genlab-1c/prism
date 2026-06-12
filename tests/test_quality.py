"""Тесты слоя скоринга: агрегация Q (harness/score/quality.py).

compute_q на синтетических конституциях — изолированно от реальных YAML.
Контракты реальной конституции проверяет test_loaders.py.
"""

from __future__ import annotations

import pytest

from harness.loaders import Constitution
from harness.score.quality import compute_q


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
