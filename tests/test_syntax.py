"""Тесты S-скорера (harness/score/syntax.py).

Два среза:
1. Без BSL LS: банды из протокола (число причин → балл), парность, кластеризация
   каскада ParseError, исключение стиля — на синтетических диагностиках.
2. Интеграция с BSL LS (skipif при отсутствии jar/java): чистый код → 10,
   сломанная парность → 0.
"""

from __future__ import annotations

import pytest

from harness.execute import bsl_ls
from harness.loaders import load_protocol_l1
from harness.score import syntax


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


BALANCED = "Функция Ф()\nКонецФункции"          # парный текст для проверок не про парность


def diag(code: str, line: int, severity: str = "error") -> dict:
    return {"code": code, "severity": severity, "message": "", "line": line}


# ── банды из протокола (число причин → балл) ─────────────────────────────────

@pytest.mark.parametrize("n,expected", [
    (0, 10), (1, 8), (2, 6), (3, 6), (4, 4), (6, 4), (7, 2), (99, 2),
])
def test_band_from_protocol(proto, n, expected):
    assert syntax.band(n, proto) == expected


# ── score_s на синтетических диагностиках ────────────────────────────────────

def test_clean_code_full_score(proto):
    s, det = syntax.score_s([], proto, BALANCED)
    assert s == 10 and det["root_causes"] == 0 and det["balanced"]


def test_single_parse_error(proto):
    s, det = syntax.score_s([diag("ParseError", 2)], proto, BALANCED)
    assert s == 8 and det["parse_error_clusters"] == 1


def test_parse_errors_cluster_as_one(proto):
    """Две ошибки в пределах cluster_gap строк — одна корневая причина."""
    s, det = syntax.score_s([diag("ParseError", 2), diag("ParseError", 4)], proto, BALANCED)
    assert det["parse_error_clusters"] == 1 and s == 8


def test_parse_errors_separate_clusters(proto):
    s, det = syntax.score_s([diag("ParseError", 2), diag("ParseError", 10)], proto, BALANCED)
    assert det["parse_error_clusters"] == 2 and s == 6


def test_compile_blocker_counts(proto):
    """compile-блокер (не ParseError) тоже корневая причина."""
    s, det = syntax.score_s([diag("ProcedureReturnsValue", 3)], proto, BALANCED)
    assert det["blockers"] == 1 and s == 8


def test_style_diagnostics_excluded(proto):
    """Стиль/стандарты не входят в S (уходят в O)."""
    s, _ = syntax.score_s([diag("OneStatementPerLine", 2, "information")], proto, BALANCED)
    assert s == 10


def test_parity_broken_is_zero(proto):
    """Функция без КонецФункции → структура разрушена → 0 минуя пороги."""
    s, det = syntax.score_s([], proto, "Функция Ф()\n    Возврат 1;")
    assert s == 0 and not det["balanced"]


def test_parity_ignores_keywords_in_strings(proto):
    """Ключевые слова внутри литералов не ломают парность."""
    s, det = syntax.score_s([], proto, 'Функция Ф()\n    Текст = "КонецФункции Цикл";\nКонецФункции')
    assert det["balanced"] and s == 10


# ── интеграция: BSL LS ───────────────────────────────────────────────────────

requires_bsl = pytest.mark.skipif(
    not bsl_ls.available(),
    reason="BSL LS не установлен (./tools/get-bsl-ls.sh) или нет java 21+")


@requires_bsl
def test_integration_clean_and_broken(proto, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.bsl").write_text("Функция Ф(А) Экспорт\n    Возврат А;\nКонецФункции\n",
                                  encoding="utf-8")
    (src / "bad.bsl").write_text("Функция Г(А) Экспорт\n    Для И = 0 По 5 Цикл\n        Возврат\n",
                                 encoding="utf-8")
    diags = bsl_ls.analyze(src, tmp_path / "out")
    s_good, _ = syntax.score_s(diags.get("good.bsl", []), proto,
                               (src / "good.bsl").read_text(encoding="utf-8"))
    s_bad, det_bad = syntax.score_s(diags.get("bad.bsl", []), proto,
                                    (src / "bad.bsl").read_text(encoding="utf-8"))
    assert s_good == 10
    assert s_bad == 0 and not det_bad["balanced"]      # обрезанная генерация
