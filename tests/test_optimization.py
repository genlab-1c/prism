"""Тесты O-скорера (harness/score/optimization.py).

Без BSL LS: банды из протокола (вес→балл), взвешенная сумма белого списка,
исключение стилевого шума, честный предел «машина не ставит O=0» —
на синтетических диагностиках. Реальные коды/веса берутся из протокола.
"""

from __future__ import annotations

import pytest

from harness.loaders import load_protocol_l1
from harness.score import optimization as o


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


def diag(code: str, line: int = 1) -> dict:
    return {"code": code, "severity": "warning", "message": "", "line": line}


# ── банды из протокола (вес → балл) ──────────────────────────────────────────


@pytest.mark.parametrize(
    "w,expected",
    [
        (0, 10),
        (1, 8),
        (2, 6),
        (3, 6),
        (3.5, 4),
        (6, 4),
        (7, 2),
        (100, 2),
    ],
)
def test_band_from_protocol(proto, w, expected):
    assert proto.scoring("O").score_for(w) == expected


# ── score_o на синтетических диагностиках ────────────────────────────────────


def test_no_antipatterns_full(proto):
    score, det = o.score_o([], proto)
    assert score == 10 and det["weighted"] == 0 and det["count"] == 0


def test_single_weight_one(proto):
    score, det = o.score_o([diag("DeprecatedCurrentDate")], proto)  # вес 1.0
    assert det["weighted"] == 1.0 and score == 8


def test_weighted_sum(proto):
    """ВТ без параметров (2.0) + соединение с подзапросом (1.5) = 3.5 → O=4."""
    score, det = o.score_o(
        [diag("VirtualTableCallWithoutParameters"), diag("JoinWithSubQuery")], proto
    )
    assert det["weighted"] == 3.5 and score == 4


def test_style_noise_excluded(proto):
    """Стилевые коды вне белого списка не влияют на O."""
    score, det = o.score_o([diag("MagicNumber"), diag("LineLength")], proto)
    assert score == 10 and det["count"] == 0


def test_machine_never_zero(proto):
    """Даже при тяжёлом весе авто-O не опускается до 0 (предел инструмента)."""
    heavy = [diag("VirtualTableCallWithoutParameters") for _ in range(10)]  # w=20
    score, _ = o.score_o(heavy, proto)
    assert score == 2 and 0 not in proto.reachable("O")
