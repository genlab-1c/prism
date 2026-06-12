"""Тесты M-скорера (harness/score/meaning.py).

Три среза:
1. Чистая логика без OneScript: band по thresholds из YAML, детект entry point,
   рендер значений tests.yaml в выражения 1С.
2. Интеграция с OneScript (skipif при отсутствии): эталон A1 обязан дать M=10,
   битый кандидат — M=0, неверная логика — частичный балл.
3. Самый ценный: canonical.bsl КАЖДОЙ задачи с тестами проходит свои тесты на 100%
   (валидация эталонов и самих тестов).
"""

from __future__ import annotations

import pytest

from harness.loaders import TaskTests, load_protocol_l1, load_tasks
from harness.score import meaning


@pytest.fixture(scope="module")
def proto():
    return load_protocol_l1()


requires_oscript = pytest.mark.skipif(
    not meaning.available(), reason="OneScript не установлен (./tools/get-onescript.sh)")


# ── band: пороги из YAML, не из кода ─────────────────────────────────────────

@pytest.mark.parametrize("passed,total,expected", [
    (4, 4, 10),     # 100%
    (9, 10, 8),     # 90%  → ≥85%
    (3, 5, 6),      # 60%
    (2, 4, 4),      # 50%
    (1, 10, 2),     # >0%
    (0, 4, 0),      # 0%
])
def test_band_thresholds(proto, passed, total, expected):
    assert meaning.band(passed, total, executed=True, protocol=proto) == expected


def test_band_not_executed_is_zero(proto):
    """Не исполнился → 0 даже при passed>0 (защита от мусорного парсинга)."""
    assert meaning.band(4, 4, executed=False, protocol=proto) == 0


def test_band_zero_total_is_zero(proto):
    assert meaning.band(0, 0, executed=True, protocol=proto) == 0


# ── детект entry point ───────────────────────────────────────────────────────

CODE_TWO_FUNCS = """
Функция Вспомогательная(Х)
    Возврат Х;
КонецФункции
Функция СортировкаПузырьком(Массив) Экспорт
    Возврат Массив;
КонецФункции
"""


def test_detect_by_pattern():
    assert meaning.detect_entry_point(CODE_TWO_FUNCS, ["Сортир\\w*"]) == "СортировкаПузырьком"


def test_detect_fallback_first_declared():
    """Паттерн не подошёл → первая объявленная функция."""
    assert meaning.detect_entry_point(CODE_TWO_FUNCS, ["НетТакой\\w*"]) == "Вспомогательная"


def test_detect_no_functions():
    assert meaning.detect_entry_point("Перем А;", ["..*"]) is None


# ── рендер значений tests.yaml → 1С ──────────────────────────────────────────

def test_value_scalars():
    assert meaning._value(None, "x") == ([], "Неопределено")
    assert meaning._value(True, "x") == ([], "Истина")
    assert meaning._value(42, "x") == ([], "42")
    assert meaning._value('а"б', "x") == ([], '"а""б"')          # экранирование кавычек


def test_value_date():
    assert meaning._value({"__date__": "2026-06-01"}, "x") == ([], "Дата(2026, 6, 1)")


def test_value_nested_array():
    stmts, expr = meaning._value([1, [2]], "М")
    assert expr == "М"
    assert "М = Новый Массив;" in stmts
    assert any("Новый Массив" in s and s.startswith("М_1") for s in stmts)


def test_value_table():
    """Маркер __table__ → ТаблицаЗначений (колонки + строки через Установить)."""
    stmts, expr = meaning._value(
        {"__table__": {"columns": ["К1", "К2"], "rows": [["а", 1]]}}, "Т")
    assert expr == "Т"
    assert "Т = Новый ТаблицаЗначений;" in stmts
    assert 'Т.Колонки.Добавить("К1");' in stmts
    assert any(".Добавить();" in s for s in stmts)
    assert any(".Установить(1, 1);" in s for s in stmts)


# ── интеграция: OneScript ────────────────────────────────────────────────────

SORT_TESTS = TaskTests(
    entry_point_patterns=["Сортир\\w*"],
    tests=[{"args": [[3, 1, 2]], "expected": [1, 2, 3]},
           {"args": [[]], "expected": []}],
)

# NB: переменную нельзя называть «И» — конфликт с ключевым словом 1С (логическое И).
# Ровно на этом валились все три модели на A1 в мартовском ретро.
GOOD_SORT = """
Функция СортировкаПузырьком(Исходный) Экспорт
    Результат = Новый Массив;
    Для Каждого Элемент Из Исходный Цикл Результат.Добавить(Элемент); КонецЦикла;
    Для Проход = 0 По Результат.Количество() - 2 Цикл
        Для Поз = 0 По Результат.Количество() - 2 - Проход Цикл
            Если Результат[Поз] > Результат[Поз + 1] Тогда
                Врем = Результат[Поз];
                Результат[Поз] = Результат[Поз + 1];
                Результат[Поз + 1] = Врем;
            КонецЕсли;
        КонецЦикла;
    КонецЦикла;
    Возврат Результат;
КонецФункции
"""


@requires_oscript
def test_good_candidate_full_score(proto, tmp_path):
    r = meaning.score_m(GOOD_SORT, SORT_TESTS, proto, tmp_path, "good")
    assert r.executed and (r.passed, r.total) == (2, 2) and r.score == 10


@requires_oscript
def test_broken_candidate_zero(proto, tmp_path):
    r = meaning.score_m("Функция Сортировка(А)\n    Возврат А;\n// нет КонецФункции",
                        SORT_TESTS, proto, tmp_path, "broken")
    assert not r.executed and r.score == 0


@requires_oscript
def test_wrong_logic_partial(proto, tmp_path):
    """Возвращает вход как есть: пустой массив пройдёт (1/2), сортировка — нет."""
    code = "Функция Сортировка(А) Экспорт\n    Возврат А;\nКонецФункции"
    r = meaning.score_m(code, SORT_TESTS, proto, tmp_path, "wrong")
    assert r.executed and (r.passed, r.total) == (1, 2) and r.score == 4   # 50%


# ── валидация эталонов: canonical обязан проходить свои тесты ────────────────

@requires_oscript
@pytest.mark.parametrize("task", [t for t in load_tasks() if t.canonical and t.testable],
                         ids=lambda t: t.id)
def test_canonical_passes_own_tests(proto, tmp_path, task):
    code = task.canonical.read_text(encoding="utf-8")
    r = meaning.score_m(code, task.tests, proto, tmp_path, f"canon_{task.id}")
    assert r.executed, r.errors
    assert r.passed == r.total, f"{task.id}: эталон прошёл {r.passed}/{r.total}: {r.errors}"
    assert r.score == 10
