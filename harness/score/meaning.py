"""Ось M (Meaning), категория A — исполнение скрытых тестов в OneScript.

Петля (протокол L1, metrics/smop_l1_auto.yaml):
 1. tests.yaml задачи: entry_point_patterns (приоритетные регэкспы) + кейсы args→expected.
 2. Имя функции детектится в коде кандидата (модели именуют по-разному).
 3. Генерируется харнесс .os: код кандидата + deep-компаратор + тесты
    (каждый в Попытка — рантайм-ошибка одного кейса не валит остальные).
 4. Запуск с таймаутом; маркеры PRISM_PASS/PRISM_FAIL/PRISM_ERR в stdout.
 5. Балл — по thresholds оси M из протокола L1 (порогов в коде нет).
    Не скомпилировался / не исполнился → 0 (execution-based: нет подтверждённого смысла).

Гейтинг: нет tools/onescript → ось «не измерена» (score=None), НЕ ноль.

Семантика сравнения: Массив — поэлементно рекурсивно; Структура — по ПОДМНОЖЕСТВУ
ключей expected (кандидат может класть дополнительные поля); null → Неопределено.
Дата в кейсах: {"__date__": "YYYY-MM-DD"}.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pydantic import BaseModel

from harness.loaders import PRISM, ProtocolL1, TaskTests

OSCRIPT = PRISM / "tools" / "onescript" / "bin" / "oscript"
FUNC_RE = re.compile(r"^\s*Функция\s+([\wа-яА-ЯёЁ]+)\s*\(", re.MULTILINE | re.IGNORECASE)
TIMEOUT_S = 15


class MeaningResult(BaseModel):
    """Итог оценки M одного кандидата."""

    score: int | None            # балл по протоколу; None = ось не измерена (нет инструмента)
    executed: bool = False       # модуль скомпилировался и исполнился
    passed: int = 0
    total: int = 0
    entry_point: str | None = None
    errors: list[str] = []


def available() -> bool:
    """Гейтинг инструмента: есть ли OneScript (tools/get-onescript.sh)."""
    return OSCRIPT.exists()


def band(passed: int, total: int, executed: bool, protocol: ProtocolL1) -> int:
    """Доля прошедших → балл по thresholds оси M из протокола L1."""
    thresholds = protocol.axes["M"].thresholds
    assert thresholds, "у оси M в протоколе L1 должны быть thresholds (машиночитаемые банды)"
    if not executed or total == 0:
        return 0
    share = passed / total
    for rule in thresholds:
        if "min_share" in rule and share >= rule["min_share"]:
            return rule["score"]
        if "gt_share" in rule and share > rule["gt_share"]:
            return rule["score"]
    return 0


def detect_entry_point(code: str, patterns: list[str]) -> str | None:
    """Первая объявленная функция, имя которой матчится приоритетным паттерном."""
    names = FUNC_RE.findall(code)
    if not names:
        return None
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for name in names:                  # порядок объявления = приоритет
            if rx.fullmatch(name):
                return name
    return names[0]


def score_m(candidate_code: str, tests: TaskTests, protocol: ProtocolL1,
            work_dir: Path, name: str = "candidate") -> MeaningResult:
    """Прогнать кейсы tests для кода кандидата; вернуть балл M по протоколу."""
    total = len(tests.tests)
    if not available():
        return MeaningResult(score=None, total=total,
                             errors=["oscript не установлен — ./tools/get-onescript.sh"])

    entry = detect_entry_point(candidate_code, tests.entry_point_patterns)
    if entry is None:
        return MeaningResult(score=band(0, total, False, protocol), total=total,
                             errors=["в коде кандидата не найдено ни одной функции"])

    harness_path = work_dir / f"{name}.test.os"
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(build_harness(candidate_code, entry, tests.tests),
                            encoding="utf-8")
    try:
        proc = subprocess.run([str(OSCRIPT), str(harness_path)],
                              capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return MeaningResult(score=band(0, total, False, protocol), total=total,
                             entry_point=entry, errors=[f"таймаут исполнения ({TIMEOUT_S}с)"])

    out = proc.stdout
    if "PRISM_BEGIN" not in out:            # модуль не скомпилировался OneScript'ом
        return MeaningResult(
            score=band(0, total, False, protocol), total=total, entry_point=entry,
            errors=[f"compile_error: {(proc.stderr or out)[-400:].strip()}"])

    passed = len(re.findall(r"^PRISM_PASS ", out, re.MULTILINE))
    errors = [line[:200] for line in out.splitlines()
              if line.startswith(("PRISM_FAIL", "PRISM_ERR"))]
    return MeaningResult(score=band(passed, total, True, protocol), executed=True,
                         passed=passed, total=total, entry_point=entry, errors=errors)


# ── генерация харнесса .os ───────────────────────────────────────────────────

def build_harness(candidate_code: str, entry_point: str, tests: list[dict]) -> str:
    # Слой совместимости: платформенные функции 1С, отсутствующие в OneScript.
    # Добавляется ТОЛЬКО если кандидат ссылается на символ (эмуляция окружения,
    # а не помощь кандидату).
    shims = "".join(impl for name, impl in _PLATFORM_SHIMS.items()
                    if re.search(rf"\b{name}\b", candidate_code, re.IGNORECASE)
                    and not re.search(rf"(?:Функция|Процедура)\s+{name}\b",
                                      candidate_code, re.IGNORECASE))
    candidate_code = candidate_code + shims
    blocks = ['Сообщить("PRISM_BEGIN");']
    for i, t in enumerate(tests):
        preamble, arg_exprs = [], []
        for j, arg in enumerate(t["args"]):
            stmts, expr = _value(arg, f"Арг_{i}_{j}")
            preamble += stmts
            arg_exprs.append(expr)
        exp_stmts, exp_expr = _value(t.get("expected"), f"Ожид_{i}")
        preamble += exp_stmts
        body = (
            "\n".join(preamble)
            + f"\nРезультат_{i} = {entry_point}({', '.join(arg_exprs)});\n"
            + f"Если ПризмаСравнить(Результат_{i}, {exp_expr}) Тогда\n"
            + f"    Сообщить(\"PRISM_PASS {i}\");\n"
            + f"Иначе\n    Сообщить(\"PRISM_FAIL {i}\");\nКонецЕсли;"
        )
        blocks.append(
            "Попытка\n" + _indent(body)
            + f"\nИсключение\n    Сообщить(\"PRISM_ERR {i} \" + ОписаниеОшибки());\nКонецПопытки;"
        )
    return candidate_code + "\n\n" + _COMPARE_FN + "\n" + "\n\n".join(blocks) + "\n"


def _value(value, name: str) -> tuple[list[str], str]:
    """Python-значение из tests.yaml → (операторы-преамбула, выражение 1С)."""
    if value is None:
        return [], "Неопределено"
    if isinstance(value, bool):
        return [], "Истина" if value else "Ложь"
    if isinstance(value, (int, float)):
        return [], str(value)
    if isinstance(value, str):
        return [], '"' + value.replace('"', '""') + '"'
    if isinstance(value, dict):
        if "__date__" in value:
            y, m, d = value["__date__"].split("-")
            return [], f"Дата({int(y)}, {int(m)}, {int(d)})"
        stmts = [f"{name} = Новый Структура;"]
        for k, (key, item) in enumerate(value.items()):
            sub_stmts, sub_expr = _value(item, f"{name}_{k}")
            stmts += sub_stmts
            stmts.append(f'{name}.Вставить("{key}", {sub_expr});')
        return stmts, name
    if isinstance(value, list):
        stmts = [f"{name} = Новый Массив;"]
        for k, item in enumerate(value):
            sub_stmts, sub_expr = _value(item, f"{name}_{k}")
            stmts += sub_stmts
            stmts.append(f"{name}.Добавить({sub_expr});")
        return stmts, name
    raise TypeError(f"неподдерживаемый тип в tests.yaml: {type(value)}")


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in text.splitlines())


# Платформенные функции 1С (8.3.x), отсутствующие в OneScript 2.0
_PLATFORM_SHIMS = {
    "ЧислоИзШестнадцатеричнойСтроки": """
Функция ЧислоИзШестнадцатеричнойСтроки(Строка)
    Цифры = "0123456789ABCDEF";
    Текст = ВРег(СокрЛП(Строка));
    Если СтрНачинаетсяС(Текст, "0X") Тогда
        Текст = Сред(Текст, 3);
    КонецЕсли;
    Результат = 0;
    Для Индекс = 1 По СтрДлина(Текст) Цикл
        Позиция = СтрНайти(Цифры, Сред(Текст, Индекс, 1));
        Если Позиция = 0 Тогда
            ВызватьИсключение "Неверная шестнадцатеричная строка";
        КонецЕсли;
        Результат = Результат * 16 + (Позиция - 1);
    КонецЦикла;
    Возврат Результат;
КонецФункции
""",
}

_COMPARE_FN = """
Функция ПризмаСравнить(Факт, Ожидание)
    Если ТипЗнч(Ожидание) = Тип("Массив") Тогда
        Если ТипЗнч(Факт) <> Тип("Массив") Тогда Возврат Ложь; КонецЕсли;
        Если Факт.Количество() <> Ожидание.Количество() Тогда Возврат Ложь; КонецЕсли;
        Для Индекс = 0 По Ожидание.Количество() - 1 Цикл
            Если НЕ ПризмаСравнить(Факт[Индекс], Ожидание[Индекс]) Тогда Возврат Ложь; КонецЕсли;
        КонецЦикла;
        Возврат Истина;
    КонецЕсли;
    Если ТипЗнч(Ожидание) = Тип("Структура") Тогда
        // подмножество: все ожидаемые ключи присутствуют и равны (лишние поля допустимы)
        Если ТипЗнч(Факт) <> Тип("Структура") Тогда Возврат Ложь; КонецЕсли;
        Для Каждого Пара Из Ожидание Цикл
            Значение = Неопределено;
            Если НЕ Факт.Свойство(Пара.Ключ, Значение) Тогда Возврат Ложь; КонецЕсли;
            Если НЕ ПризмаСравнить(Значение, Пара.Значение) Тогда Возврат Ложь; КонецЕсли;
        КонецЦикла;
        Возврат Истина;
    КонецЕсли;
    Возврат Факт = Ожидание;
КонецФункции
"""
