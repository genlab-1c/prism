"""Ось M (Meaning), категория A — исполнение скрытых тестов в OneScript.

Петля (протокол L1, metrics/smop_l1_auto.yaml):
 1. tests.yaml задачи: entry_point_patterns (приоритетные регэкспы) + кейсы args→expected.
 2. Имя функции детектится в коде кандидата (модели именуют по-разному).
 3. Генерируется харнесс .os: код кандидата + deep-компаратор + тесты
    (каждый в Попытка — рантайм-ошибка одного кейса не валит остальные).
 4. Запуск с таймаутом; маркеры PRISM_PASS/PRISM_FAIL/PRISM_ERR в stdout.
 5. Балл — по thresholds оси M из протокола L1 (порогов в коде нет).
    Не скомпилировался / не исполнился → 0 (execution-based: нет подтверждённого смысла).

Исполнение — через раннер (harness/execute/runner.py): local (хост, разработка)
или docker (песочница: без сети, лимиты; CI и недоверенные кандидаты).
Гейтинг: инструмент раннера недоступен → ось «не измерена» (score=None), НЕ ноль.

Семантика сравнения: Массив — поэлементно рекурсивно; Структура — по ПОДМНОЖЕСТВУ
ключей expected (кандидат может класть дополнительные поля); null → Неопределено.
Дата в кейсах: {"__date__": "YYYY-MM-DD"}.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from harness.execute.runner import Runner, get_runner
from harness.loaders import ProtocolL1, TaskTests

FUNC_RE = re.compile(r"^\s*Функция\s+([\wа-яА-ЯёЁ]+)\s*\(", re.MULTILINE | re.IGNORECASE)


class MeaningResult(BaseModel):
    """Итог оценки M одного кандидата."""

    score: int | None  # балл по протоколу; None = ось не измерена (нет инструмента)
    executed: bool = False  # модуль скомпилировался и исполнился
    passed: int = 0
    total: int = 0
    entry_point: str | None = None
    errors: list[str] = []


def available(runner: Runner | None = None) -> bool:
    """Гейтинг инструмента: доступен ли раннер (local: oscript; docker: образ)."""
    return (runner or get_runner()).available()


def band(passed: int, total: int, executed: bool, protocol: ProtocolL1) -> int:
    """Доля прошедших → СТУПЕНЬКА оси M (0..10 через одну).

    Это проекция плавного сигнала на 6-ступенчатую шкалу — нужна ТОЛЬКО для оценки
    согласия с экспертом (каппа Коэна), у которого иной шкалы нет. На лидерборд идёт
    плавная оценка (см. fine_m). Гард: не исполнился / нет тестов → 0 минуя таблицу.
    """
    if not executed or total == 0:
        return 0
    return protocol.scoring("M").score_for(passed / total)


def fine_m(passed: int, total: int, executed: bool) -> float:
    """Плавная оценка M на шкале 0..10 = доля прошедших × 10 (хранимая, лидербордная).

    Машина мерит долю напрямую и не загоняет её в ступеньки — это снимает мёртвые
    зоны 6-балльной шкалы (напр. 4/5=80% даёт 8.0, а не округляется до ступеньки 6).
    Гард тот же, что у band: не исполнился / нет тестов → 0.0 (нет подтверждённого смысла).
    """
    if not executed or total == 0:
        return 0.0
    return round(passed / total * 10, 1)


def detect_entry_point(code: str, patterns: list[str]) -> str | None:
    """Первая объявленная функция, имя которой матчится приоритетным паттерном."""
    names = FUNC_RE.findall(code)
    if not names:
        return None
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for name in names:  # порядок объявления = приоритет
            if rx.fullmatch(name):
                return name
    return names[0]


def score_m(
    candidate_code: str,
    tests: TaskTests,
    protocol: ProtocolL1,
    work_dir: Path,
    name: str = "candidate",
    runner: Runner | None = None,
) -> MeaningResult:
    """Прогнать кейсы tests для кода кандидата; вернуть балл M по протоколу.

    runner — режим исполнения (по умолчанию из env PRISM_RUNNER: local | docker).
    """
    runner = runner or get_runner()
    total = len(tests.tests)
    if not runner.available():
        return MeaningResult(score=None, total=total, errors=[runner.unavailable_reason()])

    entry = detect_entry_point(candidate_code, tests.entry_point_patterns)
    if entry is None:
        return MeaningResult(
            score=band(0, total, False, protocol),
            total=total,
            errors=["в коде кандидата не найдено ни одной функции"],
        )

    harness_path = work_dir / f"{name}.test.os"
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(build_harness(candidate_code, entry, tests.tests), encoding="utf-8")
    res = runner.run_os(harness_path)
    if res.timed_out:
        return MeaningResult(
            score=band(0, total, False, protocol),
            total=total,
            entry_point=entry,
            errors=["таймаут исполнения"],
        )

    if "PRISM_BEGIN" not in res.stdout:  # модуль не скомпилировался OneScript'ом
        return MeaningResult(
            score=band(0, total, False, protocol),
            total=total,
            entry_point=entry,
            errors=[f"compile_error: {(res.stderr or res.stdout)[-400:].strip()}"],
        )

    passed = len(re.findall(r"^PRISM_PASS ", res.stdout, re.MULTILINE))
    errors = [
        line[:200]
        for line in res.stdout.splitlines()
        if line.startswith(("PRISM_FAIL", "PRISM_ERR"))
    ]
    return MeaningResult(
        score=band(passed, total, True, protocol),
        executed=True,
        passed=passed,
        total=total,
        entry_point=entry,
        errors=errors,
    )


# ── генерация харнесса .os ───────────────────────────────────────────────────


def _strip_module_body(code: str) -> str:
    """Убрать тело модуля — исполняемый код ПОСЛЕ последнего объявления функции/процедуры.

    Модели часто дописывают «пример использования» (топ-левел `Сообщить(...)` и т.п.), а
    харнесс клеит свои функции (шимы, компаратор) после кода кандидата. В 1С функции нельзя
    объявлять после операторов модуля → ошибка компиляции, и корректное решение получает 0.
    Срезаем всё после последнего КонецФункции/КонецПроцедуры (объявления и Перем выше — целы).
    Поиск построчный и устойчив к строкам/комментариям; нет объявлений → код не трогаем.
    """
    lines = code.splitlines()
    last = -1
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):  # продолжение многострочной строки — не код
            continue
        neutral = re.sub(r'"(?:[^"]|"")*"?', " ", line).split("//", 1)[0]  # без литералов/комментов
        if re.search(r"\b(?:КонецФункции|КонецПроцедуры)\b", neutral, re.IGNORECASE):
            last = i
    if last == -1:
        return code
    kept = "\n".join(lines[: last + 1])
    # хвостовой `;` после последнего КонецФункции/КонецПроцедуры — пустой оператор тела
    # модуля, тоже ломает дописываемые функции; убираем
    return re.sub(r"(КонецФункции|КонецПроцедуры)\s*;\s*$", r"\1", kept, flags=re.IGNORECASE)


def build_harness(candidate_code: str, entry_point: str, tests: list[dict]) -> str:
    candidate_code = _strip_module_body(candidate_code)  # убрать демо-код после объявлений
    # Слой совместимости: платформенные функции 1С, отсутствующие в OneScript.
    # Добавляется ТОЛЬКО если кандидат ссылается на символ (эмуляция окружения,
    # а не помощь кандидату).
    shims = "".join(
        impl
        for name, impl in _PLATFORM_SHIMS.items()
        if re.search(rf"\b{name}\b", candidate_code, re.IGNORECASE)
        and not re.search(rf"(?:Функция|Процедура)\s+{name}\b", candidate_code, re.IGNORECASE)
    )
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
            + f'    Сообщить("PRISM_PASS {i}");\n'
            + f'Иначе\n    Сообщить("PRISM_FAIL {i}");\nКонецЕсли;'
        )
        blocks.append(
            "Попытка\n"
            + _indent(body)
            + f'\nИсключение\n    Сообщить("PRISM_ERR {i} " + ОписаниеОшибки());\nКонецПопытки;'
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
        if "__table__" in value:  # ТаблицаЗначений: {columns, rows}
            spec = value["__table__"]
            stmts = [f"{name} = Новый ТаблицаЗначений;"]
            for col in spec["columns"]:
                stmts.append(f'{name}.Колонки.Добавить("{col}");')
            for r, row in enumerate(spec["rows"]):
                stmts.append(f"{name}_с{r} = {name}.Добавить();")
                for c, cell in enumerate(row):
                    sub_stmts, sub_expr = _value(cell, f"{name}_{r}_{c}")
                    stmts += sub_stmts
                    stmts.append(f"{name}_с{r}.Установить({c}, {sub_expr});")
            return stmts, name
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
    Если ТипЗнч(Ожидание) = Тип("ТаблицаЗначений") Тогда
        Если ТипЗнч(Факт) <> Тип("ТаблицаЗначений") Тогда Возврат Ложь; КонецЕсли;
        Если Факт.Количество() <> Ожидание.Количество() Тогда Возврат Ложь; КонецЕсли;
        Если Факт.Колонки.Количество() <> Ожидание.Колонки.Количество() Тогда Возврат Ложь; КонецЕсли;
        // строки сравниваем БЕЗ учёта порядка (значения по индексу колонки), без повторного зачёта
        Зачтённые = Новый Массив;
        Для Каждого ОжСтрока Из Ожидание Цикл
            Найдена = Ложь;
            Для Индекс = 0 По Факт.Количество() - 1 Цикл
                Если Зачтённые.Найти(Индекс) <> Неопределено Тогда Продолжить; КонецЕсли;
                Совпало = Истина;
                Для К = 0 По Ожидание.Колонки.Количество() - 1 Цикл
                    Если НЕ ПризмаСравнить(Факт[Индекс][К], ОжСтрока[К]) Тогда Совпало = Ложь; Прервать; КонецЕсли;
                КонецЦикла;
                Если Совпало Тогда Найдена = Истина; Зачтённые.Добавить(Индекс); Прервать; КонецЕсли;
            КонецЦикла;
            Если НЕ Найдена Тогда Возврат Ложь; КонецЕсли;
        КонецЦикла;
        Возврат Истина;
    КонецЕсли;
    Возврат Факт = Ожидание;
КонецФункции
"""
