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
    assert r.platform_errors == [] and r.platform_error_tests == 0  # FAIL — ось M, не P


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
    assert _count_platform_error_tests(log) == 1  # только тест3


def test_generic_exception_is_not_platform_error():
    """Исключение без платформенного маркера (напр. деление на 0) → не ось P."""
    assert _count_platform_error_tests("тест1 ИСКЛЮЧЕНИЕ: Деление на 0") == 0


def test_counts_multiple_platform_errors():
    log = (
        "тест1 ИСКЛЮЧЕНИЕ: Поле не найдено; "
        "тест2 FAIL значение неверное; "
        "тест3 ИСКЛЮЧЕНИЕ: Метод объекта не обнаружен"
    )
    assert _count_platform_error_tests(log) == 2


def test_platform_error_counted_even_when_test_wrote_it_as_fail():
    """Тест сам поймал исключение и записал его как FAIL — балл P не должен от этого зависеть.

    Раньше засчитывалось только слово ИСКЛЮЧЕНИЕ, и оформление tests.bsl сдвигало балл:
    на B5 три теста упали на одной платформенной ошибке, а P выходил 3.3 вместо 0.
    """
    log = "тест1 FAIL (Поле не найдено: Номенклатура.Артикул); тест2 FAIL ожидали 10, получили 8"
    assert _count_platform_error_tests(log) == 1  # только первый, второй — неверный ответ


def test_virtual_table_call_is_a_platform_error():
    """Виртуальная таблица регистра вызвана неверно — это знание платформы, ось P.

    Список маркеров знал ровно «(Выполнить)», поэтому обращения к менеджерам регистров
    проходили мимо и запись получала P=10 при полностью упавших тестах.
    """
    log = (
        "тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Остатки): "
        "Недопустимое значение параметра (параметр номер '3')"
    )
    assert _count_platform_error_tests(log) == 1


def test_write_to_readonly_metadata_field_is_a_platform_error():
    log = "тест1 ИСКЛЮЧЕНИЕ: Поле объекта недоступно для записи (ВидСчета)"
    assert _count_platform_error_tests(log) == 1


def test_collection_methods_stay_on_axis_m():
    """Имена, которые есть и у обычных коллекций, в маркеры не берём.

    Разбор кода кандидатов (bsl-expert, 2026-09-18) показал: под «(Добавить)» и
    «(Сортировать)» лежит работа с ТаблицаЗначений, а не с метаданными, и отличить
    платформенный случай от общего по тексту исключения нельзя — нужен исходник.
    Пока классификатор видит только лог, такие ошибки остаются на оси M.
    """
    from harness.execute.onec.runner import platform_error_markers

    ambiguous = (
        "Выбрать",
        "Получить",
        "Добавить",
        "Найти",
        "Записать",
        "Прочитать",
        "Установить",
        "Выгрузить",
        "Загрузить",
        "Сортировать",
        "Свернуть",
    )
    for name in ambiguous:
        assert f"Ошибка при вызове метода контекста ({name})" not in platform_error_markers()
    log = (
        "тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Добавить): "
        "Несоответствие типов (параметр номер '2')"
    )
    assert _count_platform_error_tests(log) == 0


def test_manager_only_methods_are_platform_errors():
    """Методы, которых у коллекций BSL нет, однозначно указывают на объект метаданных."""
    for name in ("ВыбратьИерархически", "НайтиПоКоду", "СоздатьНаборЗаписей", "СрезПоследних"):
        log = f"тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста ({name}): Несоответствие типов"
        assert _count_platform_error_tests(log) == 1, name


def test_query_language_error_belongs_to_axis_m_not_p():
    """Кривой текст запроса — авторство кода, а не знание метаданных.

    По конституции ошибки текста запроса идут в M. И они УЖЕ наказаны: запрос не
    выполнился → тест провалился → M упала. Считать их ещё и провалом P значит
    наказывать дважды за одно.
    """
    for text in (
        "Синтаксическая ошибка",
        "Не допускается использование вложенных запросов",
        "Неоднозначное поле",
        "Не задано значение параметра",
    ):
        log = f"тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): {text} «Товар»"
        assert _count_platform_error_tests(log) == 0, text


def test_metadata_error_under_the_same_marker_stays_on_axis_p():
    """Под тем же маркером «(Выполнить)» лежит и обращение к несуществующим метаданным."""
    for text in (
        "Поле не найдено",
        "Таблица не найдена",
        'Неверные параметры "РегистрНакопления.Х"',
    ):
        log = f"тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): {text}"
        assert _count_platform_error_tests(log) == 1, text


def test_unknown_text_under_a_marker_is_still_counted_as_platform():
    """Маркер сработал, подкласс неизвестен — считаем P и показываем текст в аудите.

    Обратное (молча не считать) тихо завышало бы P на каждом новом тексте ошибки 1С.
    """
    log = "тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): Неведомая беда"
    assert _count_platform_error_tests(log) == 1


def test_markers_come_from_the_taxonomy_not_from_code():
    """Словарь — данные: раннер читает metrics/error_taxonomy.yaml, а не держит список у себя."""
    from harness.execute.onec.runner import platform_error_markers
    from harness.loaders import load_error_taxonomy

    assert set(platform_error_markers()) == set(load_error_taxonomy()["platform_error_markers"])


def test_log_is_kept_long_enough_to_classify():
    """Лог режется не на 500 символах: на них сообщения рвались на полуслове и аудит
    не мог перепроверить балл P по сохранённым данным."""
    from harness.execute.onec.runner import LOG_LIMIT

    tail = "; ".join(
        f"тест{i} ИСКЛЮЧЕНИЕ: Поле не найдено (Номенклатура.Реквизит{i})" for i in range(12)
    )
    r = parse_result(f"PASSED=0;TOTAL=12;{tail}")
    assert len(tail) > 500 and r.log == tail  # целиком, потому что короче лимита
    assert LOG_LIMIT >= 4000


# ── _parse_compile_log: строки и тексты ошибок компиляции (ось S кат. B) ──────


def test_compile_log_parsing():
    text = (
        "{ОбщийМодуль.КодКандидата.Модуль(12,5)}: Перем: ожидается имя переменной\n"
        "{ОбщийМодуль.КодКандидата.Модуль(20)}: Неизвестный идентификатор"
    )
    lines, errors = _parse_compile_log(text)
    assert lines == [12, 20]
    assert "ожидается имя переменной" in errors[0]


# ── код завершения компилятора платформы ─────────────────────────────────────


def test_read_rc_parses_exit_code(tmp_path):
    """Скрипт контейнера пишет код завершения шага в файл; читаем число, мусор → None."""
    from harness.execute.onec.runner import _read_rc

    (tmp_path / "check.rc").write_text("139\n", encoding="utf-8")
    assert _read_rc(tmp_path / "check.rc") == 139
    (tmp_path / "bad.rc").write_text("segfault", encoding="utf-8")
    assert _read_rc(tmp_path / "bad.rc") is None
    assert _read_rc(tmp_path / "нет.rc") is None
