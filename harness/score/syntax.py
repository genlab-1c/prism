"""Ось S (Syntax), категория A — компилируемость по статическому парсеру BSL LS.

Петля (протокол L1, metrics/smop_l1_auto.yaml, ось S):
 1. pre_check парности (Функция/КонецФункции, Если, Цикл, Попытка) на тексте без
    строк/комментариев: дисбаланс → S=0 (ловит обрезанную генерацию, которую
    парсер молча проглатывает).
 2. Иначе число КОРНЕВЫХ причин n = кластеры ParseError (каскад ≤cluster_gap строк =
    одна причина) + compile-блокеры (compile_blocker_codes из протокола).
 3. Вердикт «собирается ли» даёт движок, который код ИСПОЛНЯЕТ (compile_check протокола):
    BSL LS — парсер, а не компилятор, и снисходителен. Если движок модуль не разобрал,
    причин не может быть ноль: n = max(n, 1). Ошибки разрешения имён (not_syntax) в счёт
    не идут — по конституции несуществующие имена вне оси S.
 4. Балл — по thresholds оси S из протокола L1 (порогов в коде нет).

Стиль/стандарты (OneStatementPerLine, DeprecatedCurrentDate, …) в S НЕ входят —
они уходят в O (см. excludes протокола). Диагностики даёт harness/execute/bsl_ls.py;
инструмент недоступен → ось «не измерена» (score=None) выше по стеку, в оркестраторе.
"""

from __future__ import annotations

import re

from harness.loaders import ProtocolL1

# Структурная парность: открывающее ключевое слово → закрывающее.
# Считаем ОБА языка: BSL принимает и русские, и английские ключевые слова, а модели их мешают
# в одном модуле. Видя только русские, проверка слепла на английских открывашках и звала
# сбалансированным код с незакрытым `for each … do` (наблюдалось у GigaChat).
_PAIRS = (
    (r"\bфункция\b|\bfunction\b", r"\bконецфункции\b|\bendfunction\b"),
    (r"\bпроцедура\b|\bprocedure\b", r"\bконецпроцедуры\b|\bendprocedure\b"),
    (r"\bесли\b|\bif\b", r"\bконецесли\b|\bendif\b"),
    (r"\bцикл\b|\bdo\b", r"\bконеццикла\b|\benddo\b"),
    (r"\bпопытка\b|\btry\b", r"\bконецпопытки\b|\bendtry\b"),
)


def compile_verdict(output: str, protocol: ProtocolL1) -> tuple[bool, str]:
    """Разобрал ли движок модуль. Возвращает (разобран, текст первой значимой ошибки).

    Ошибки разрешения имён (`Symbol not found` и т.п.) считаем «разобран»: по конституции
    несуществующие имена — не синтаксис, они проявятся на осях M/P. Так вердикт не зависит
    от того, насколько словарь движка совпадает с платформой (пробелы OneScript — отдельная тема).
    """
    check = protocol.axes["S"].compile_check or {}
    text = (output or "").strip()
    if not text or (check.get("clean_marker") or "No errors.") in text:
        return True, ""
    if any(marker in text for marker in check.get("not_syntax") or []):
        return True, ""
    return False, text.splitlines()[0][:200] if text else ""


def score_s(
    diagnostics: list[dict],
    protocol: ProtocolL1,
    module_text: str | None = None,
    compile_output: str | None = None,
) -> tuple[int, dict]:
    """S = компилируемость: парность + причины парсера + вердикт движка → балл."""
    s_axis = protocol.axes["S"]
    gap = s_axis.cluster_gap or 3
    blocker_codes = set(s_axis.compile_blocker_codes or [])

    balanced, balance_detail = (True, {}) if module_text is None else _check_balance(module_text)
    parse_errors = [d for d in diagnostics if d["code"] == "ParseError"]
    clusters = _cluster_lines(sorted(d["line"] for d in parse_errors), gap)
    blockers = [d for d in diagnostics if d["code"] in blocker_codes]
    n = clusters + len(blockers)

    parsed, compile_error = (True, "")
    if compile_output is not None:
        parsed, compile_error = compile_verdict(compile_output, protocol)
        if not parsed:
            n = max(n, 1)  # движок не собрал — значит причина есть, сколько именно, он не скажет

    score = 0 if not balanced else protocol.scoring("S").score_for(n)  # pre_check → 0 минуя таблицу
    detail = {
        "root_causes": n,
        "parse_error_clusters": clusters,
        "blockers": len(blockers),
        "balanced": balanced,
        "balance_detail": balance_detail,
        "error_codes": sorted({d["code"] for d in parse_errors + blockers}),
    }
    if compile_output is not None:
        detail["engine_parsed"] = parsed
        if compile_error:
            detail["engine_error"] = compile_error
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
        if line.lstrip().startswith("|"):  # продолжение многострочной строки
            continue
        line = re.sub(r'"(?:[^"]|"")*"?', " ", line)  # литералы (в т.ч. незакрытые)
        line = line.split("//", 1)[0]
        out.append(line)
    return "\n".join(out)
