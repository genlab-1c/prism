"""Тесты оси P (score_p) — балл из результата исполнения, без 1С/Docker.

Проверяем разделение вины (инфраструктура → «не измерено» None, вина кандидата → 0)
и плавную долю чистых тестов clean/total → ступенька P по протоколу. OneCRunResult
конструируется синтетически — реальный прогон 1С не нужен.
"""
from __future__ import annotations

import pytest

from harness.execute.onec.runner import OneCRunResult
from harness.loaders import load_protocol_l1
from harness.score.platform import score_p


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


# ── разделение вины: инфраструктура → «не измерено» (None, НЕ 0) ──────────────

@pytest.mark.parametrize("status", ["infra_error", "no_result"])
def test_infra_not_measured(proto, status):
    band, detail = score_p(OneCRunResult(status=status, infra_detail="docker недоступен"), proto)
    assert band is None
    assert "не состоялось" in detail["reason"]


# ── вина кандидата: нет функции / не компилируется → 0 ────────────────────────

@pytest.mark.parametrize("status", ["no_entry", "candidate_error"])
def test_candidate_fault_is_zero(proto, status):
    band, _ = score_p(OneCRunResult(status=status), proto)
    assert band == 0


# ── плавная доля clean/total → ступенька P (достижимы {0,4,6,10}) ─────────────

@pytest.mark.parametrize("total,bad,expected", [
    (5, 0, 10),   # все обращения к метаданным отработали (100% чистых)
    (4, 1, 6),    # 75% чистых → ≥0.5
    (4, 2, 6),    # 50% → ≥0.5
    (4, 3, 4),    # 25% → >0
    (4, 4, 0),    # 0% чистых → структура обращений вымышлена
])
def test_clean_share_to_band(proto, total, bad, expected):
    run = OneCRunResult(status="ok", passed=total - bad, total=total,
                        platform_error_tests=bad,
                        platform_errors=["Поле не найдено"] if bad else [])
    band, detail = score_p(run, proto)
    assert band == expected
    assert detail["clean_share"] == round((total - bad) / total, 3)


# ── обработчик упал ДО тестов (total=0) ───────────────────────────────────────

def test_crashed_before_tests_with_marker_is_zero(proto):
    """total=0, но есть платформенный маркер → структура вымышлена → 0."""
    run = OneCRunResult(status="ok", total=0, platform_errors=["Объект не найден"])
    band, detail = score_p(run, proto)
    assert band == 0 and detail["clean_share"] == 0.0


def test_crashed_before_tests_no_marker_not_measured(proto):
    """total=0 и платформенных маркеров нет → не измерено (None), а не 0."""
    band, detail = score_p(OneCRunResult(status="ok", total=0), proto)
    assert band is None and "не исполнились" in detail["reason"]
