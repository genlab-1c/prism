"""Тесты парсера результата прогона категории B (чистые функции, без 1С/Docker).

parse_result и _count_platform_error_tests задают ГРАНИЦУ осей P и M: платформенная
ошибка (обращение к несуществующим метаданным) считается провалом P, а просто неверный
ответ (FAIL по значению) — это ось M и в P не идёт. Поломка этой логики молча сместит
баллы всей категории B, поэтому граница закреплена тестами.
"""
from __future__ import annotations

from harness.execute.onec.runner import (
    _count_platform_error_tests,
    _parse_compile_log,
    parse_result,
)


# ── parse_result: PASSED/TOTAL + классификация ────────────────────────────────

def test_passed_total_without_platform_error():
    r = parse_result("PASSED=3;TOTAL=5;тест4 FAIL ожидали 10, получили 8")
    assert r.status == "ok" and (r.passed, r.total) == (3, 5)
    assert r.platform_errors == [] and r.platform_error_tests == 0   # FAIL — ось M, не P


def test_platform_error_marked_and_counted():
    log = "PASSED=2;TOTAL=4;тест3 ИСКЛЮЧЕНИЕ: Поле не найдено (Номенклатура.Характеристика)"
    r = parse_result(log)
    assert (r.passed, r.total) == (2, 4)
    assert "Поле не найдено" in r.platform_errors
    assert r.platform_error_tests == 1


def test_crash_before_tests_has_no_passed_total():
    """Нет 'PASSED=…;TOTAL=…' (обработчик упал до тестов) → total=0, маркер пойман."""
    r = parse_result("КЛИЕНТ_ИСКЛЮЧЕНИЕ: Объект не найден: Справочник.Контрагенты")
    assert r.status == "ok" and (r.passed, r.total) == (0, 0)
    assert "Объект не найден" in r.platform_errors


# ── _count_platform_error_tests: граница P↔M ──────────────────────────────────

def test_fail_is_not_platform_error():
    """Неверный ответ (FAIL) — ось M; платформенным провалом не считается."""
    log = "тест2 FAIL значение; тест3 ИСКЛЮЧЕНИЕ: Таблица не найдена"
    assert _count_platform_error_tests(log) == 1                     # только тест3


def test_generic_exception_is_not_platform_error():
    """Исключение без платформенного маркера (напр. деление на 0) → не ось P."""
    assert _count_platform_error_tests("тест1 ИСКЛЮЧЕНИЕ: Деление на 0") == 0


def test_counts_multiple_platform_errors():
    log = ("тест1 ИСКЛЮЧЕНИЕ: Поле не найдено; "
           "тест2 FAIL значение неверное; "
           "тест3 ИСКЛЮЧЕНИЕ: Метод объекта не обнаружен")
    assert _count_platform_error_tests(log) == 2


# ── _parse_compile_log: строки и тексты ошибок компиляции (ось S кат. B) ──────

def test_compile_log_parsing():
    text = ("{ОбщийМодуль.КодКандидата.Модуль(12,5)}: Перем: ожидается имя переменной\n"
            "{ОбщийМодуль.КодКандидата.Модуль(20)}: Неизвестный идентификатор")
    lines, errors = _parse_compile_log(text)
    assert lines == [12, 20]
    assert "ожидается имя переменной" in errors[0]
