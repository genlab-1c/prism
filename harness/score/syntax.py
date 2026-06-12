"""Ось S (Syntax), категория A — компилируемость по статическому парсеру BSL LS.

Петля (протокол L1, metrics/smop_l1_auto.yaml, ось S):
 1. pre_check парности (Функция/КонецФункции, Если, Цикл, Попытка) на тексте без
    строк/комментариев: дисбаланс → S=0 (ловит обрезанную генерацию, которую
    парсер молча проглатывает).
 2. Иначе число КОРНЕВЫХ причин n = кластеры ParseError (каскад ≤cluster_gap строк =
    одна причина) + compile-блокеры (compile_blocker_codes из протокола).
 3. Балл — по thresholds оси S из протокола L1 (порогов в коде нет).

Стиль/стандарты (OneStatementPerLine, DeprecatedCurrentDate, …) в S НЕ входят —
они уходят в O (см. excludes протокола). Диагностики даёт harness/execute/bsl_ls.py;
инструмент недоступен → ось «не измерена» (score=None) выше по стеку, в оркестраторе.
"""

from __future__ import annotations

import re

from harness.loaders import ProtocolL1

# Структурная парность: открывающее ключевое слово → закрывающее
_PAIRS = (
    (r"\bфункция\b", r"\bконецфункции\b"),
    (r"\bпроцедура\b", r"\bконецпроцедуры\b"),
    (r"\bесли\b", r"\bконецесли\b"),
    (r"\bцикл\b", r"\bконеццикла\b"),
    (r"\bпопытка\b", r"\bконецпопытки\b"),
)


def band(n_causes: int, protocol: ProtocolL1) -> int:
    """Число корневых причин → балл по thresholds оси S из протокола L1."""
    thresholds = protocol.axes["S"].thresholds
    assert thresholds, "у оси S в протоколе L1 должны быть thresholds (машиночитаемые банды)"
    for rule in thresholds:
        if "max_causes" in rule and n_causes <= rule["max_causes"]:
            return rule["score"]
        if "gt_causes" in rule and n_causes > rule["gt_causes"]:
            return rule["score"]
    return 0


def score_s(diagnostics: list[dict], protocol: ProtocolL1,
            module_text: str | None = None) -> tuple[int, dict]:
    """S = компилируемость: парность + кластеры ParseError + compile-блокеры → балл."""
    s_axis = protocol.axes["S"]
    gap = s_axis.cluster_gap or 3
    blocker_codes = set(s_axis.compile_blocker_codes or [])

    balanced, balance_detail = (True, {}) if module_text is None else _check_balance(module_text)
    parse_errors = [d for d in diagnostics if d["code"] == "ParseError"]
    clusters = _cluster_lines(sorted(d["line"] for d in parse_errors), gap)
    blockers = [d for d in diagnostics if d["code"] in blocker_codes]
    n = clusters + len(blockers)

    score = 0 if not balanced else band(n, protocol)
    detail = {
        "root_causes": n,
        "parse_error_clusters": clusters,
        "blockers": len(blockers),
        "balanced": balanced,
        "balance_detail": balance_detail,
        "error_codes": sorted({d["code"] for d in parse_errors + blockers}),
    }
    return score, detail


# ── внутреннее ───────────────────────────────────────────────────────────────

def _cluster_lines(lines: list[int], gap: int) -> int:
    """Число кластеров: соседние ParseError (≤gap строк) — одна корневая причина."""
    clusters = 0
    prev = None
    for line in lines:
        if prev is None or line - prev > gap:
            clusters += 1
        prev = line
    return clusters


def _check_balance(text: str) -> tuple[bool, dict]:
    """Парность Функция/КонецФункции и т.п. на тексте без строк и комментариев."""
    code = _strip_strings_and_comments(text).lower()
    detail, balanced = {}, True
    for opener, closer in _PAIRS:
        n_open = len(re.findall(opener, code))
        n_close = len(re.findall(closer, code))
        if n_open != n_close:
            balanced = False
            detail[opener.strip(r"\b")] = {"open": n_open, "close": n_close}
    return balanced, detail


def _strip_strings_and_comments(text: str) -> str:
    """Убрать строковые литералы (включая |-продолжения запросов) и // комментарии."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):              # продолжение многострочной строки
            continue
        line = re.sub(r'"(?:[^"]|"")*"?', " ", line)   # литералы (в т.ч. незакрытые)
        line = line.split("//", 1)[0]
        out.append(line)
    return "\n".join(out)
