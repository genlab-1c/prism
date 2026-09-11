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


# ── подмена встроенных команд (cost_model.instrument) ────────────────────────
#
# Подмена обслуживает ЗАМЕРОЧНЫЙ прогон, поэтому её единственное жёсткое требование —
# не менять смысл и не ломать код. Здесь проверяются формы, на которых она ломалась:
# приёмник через точку и вызовы с числом аргументов, которого аналог не принимает.


def test_receiver_keeps_full_chain():
    """Приёмник — всё выражение слева от точки, иначе теряется его начало.

    `ИсходнаяТаблица.Колонки.Найти(Имя)` с потерей префикса давал
    `ПризмаНайти(Колонки, Имя)` и рабочий код падал на «Symbol not found Колонки».
    """
    from harness.score.cost_model import instrument

    assert instrument("Поз = ТЗ.Колонки.Найти(Имя);") == "Поз = ПризмаНайти(ТЗ.Колонки, Имя);"


@pytest.mark.parametrize(
    "code",
    [
        "Рез = Кэш[Ключ].Найти(Э);",
        "Рез = ПолучитьТаблицу().Найти(Э);",
        "Рез = А.Б.В.Найти(Э);",
    ],
)
def test_receiver_forms_are_passed_whole(code):
    """Индексация, вызов и длинная цепочка — приёмник попадает первым аргументом целиком."""
    from harness.score.cost_model import instrument

    out = instrument(code)
    receiver = code.split(".Найти(")[0].split("= ")[1]
    assert f"ПризмаНайти({receiver}, " in out


def test_table_find_with_columns_keeps_both_arguments():
    """ТаблицаЗначений.Найти(Знач, "Колонка") — штатная форма 1С, её надо мерить, а не ломать."""
    from harness.score.cost_model import instrument

    assert (
        instrument('Стр = ТЗ.Найти(Знач, "Колонка");') == 'Стр = ПризмаНайти(ТЗ, Знач, "Колонка");'
    )


@pytest.mark.parametrize(
    "code",
    [
        "МассивСлов.Удалить(, МассивСлов.Количество() - 2);",  # пропущен первый аргумент
        "Слово.Удалить(0, 5);",  # у строки такого метода нет — форма не наша
        "Таблица.НайтиСтроки(Отбор, Ещё);",  # второго параметра у аналога нет
    ],
)
def test_unsupported_call_shape_is_left_alone(code):
    """Форму, которую аналог не принимает, не трогаем: иначе ломаем код своей подменой."""
    from harness.score.cost_model import instrument

    assert instrument(code) == code


def test_table_insert_single_argument_supported():
    """ТаблицаЗначений.Вставить(Индекс) возвращает строку — аналог тоже функция."""
    from harness.score.cost_model import instrument

    assert instrument("Новая = ТЗ.Вставить(0);") == "Новая = ПризмаВставить(ТЗ, 0);"


def test_substitution_skipped_inside_strings_and_comments():
    """Строковые литералы и комментарии не трогаются (главная хрупкость регэкспов)."""
    from harness.score.cost_model import instrument

    code = '// Массив.Найти(Э)\nТекст = "Массив.Найти(Э)";'
    assert instrument(code) == code


def test_helpers_declare_all_analogs():
    """Каждый аналог из карты объявлен в блоке хелперов — иначе замер падает на имени."""
    from harness.score.cost_model import _METHOD_ANALOGS, _METHOD_ARITY, HELPERS

    for method, analog in _METHOD_ANALOGS.items():
        assert f"Функция {analog}(" in HELPERS or f"Процедура {analog}(" in HELPERS
        assert method in _METHOD_ARITY


# ── перевод координат ошибки в строки кода модели ────────────────────────────


def test_error_line_translated_to_model_line():
    """В замерочном файле код модели идёт после хелперов: сырой номер сбивает с толку."""
    from harness.score.cost_model import HELPERS_LINES
    from harness.score.optimization_exec import _locate

    raw = (
        f"{{Модуль /sandbox/cand.operf.os / Error in line: {HELPERS_LINES + 15} / "
        "Symbol not found Колонки}"
    )
    line, message = _locate(raw, HELPERS_LINES + 40)
    assert (line, message) == (15, "Symbol not found Колонки")


def test_error_line_with_column_form():
    """Вторая форма сообщения OneScript — «line 94,51» без двоеточия."""
    from harness.score.cost_model import HELPERS_LINES
    from harness.score.optimization_exec import _locate

    raw = f"{{Модуль / Error in line {HELPERS_LINES + 5},51 / Too many actual parameters}}"
    assert _locate(raw, HELPERS_LINES + 40)[0] == 5


@pytest.mark.parametrize("shift,mark", [(-10, "хелпер"), (100, "perf.yaml")])
def test_error_outside_model_code_is_labelled(shift, mark):
    """Ошибка в хелперах или в генераторе входа — не строка модели, и это надо сказать."""
    from harness.score.cost_model import HELPERS_LINES
    from harness.score.optimization_exec import _locate

    raw = f"{{Модуль / Error in line: {HELPERS_LINES + shift} / сбой}}"
    line, message = _locate(raw, HELPERS_LINES + 40)
    assert line is None and mark in message
