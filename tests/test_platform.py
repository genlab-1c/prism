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


# ── модуль не дошёл до базы → «не измерено» (не ноль) ─────────────────────────


@pytest.mark.parametrize("status", ["no_entry", "candidate_error"])
def test_module_that_never_reached_the_base_is_not_measured(proto, status):
    """Ноль утверждал бы, что обращения к метаданным были и оказались неверными.

    Их не проверяли: модуль с одной опечаткой мог ссылаться на метаданные безупречно.
    Оси SMOP независимы по смыслу, но у P и M один канал измерения (прогон 1С), и
    молчание канала — отсутствие свидетельства, а не свидетельство против. Вина
    кандидата наказана там, где она измерена: S за несобираемость, M за тесты.
    До протокола 1.5.0 здесь стоял 0, и он держался заплаткой на формуле Q.
    """
    band, detail = score_p(OneCRunResult(status=status), proto)
    assert band is None
    assert detail["unmeasured"] == status and detail["reason"].startswith("не измерено")


def test_unparsed_query_is_dropped_from_the_denominator(proto):
    """Тест, чей запрос не разобрался, не «чистый» и не «провал» — его просто нет в доле.

    Считать его чистым значило бы поставить P=10 «все обращения к метаданным отработали»
    там, где ни одного обращения не проверялось: платформа до имён не дошла.
    """
    run = OneCRunResult(status="ok", passed=0, total=3, platform_error_tests=0, unverified_tests=2)
    band, detail = score_p(run, proto)
    assert detail["judged"] == 1 and detail["clean"] == 1
    assert band == 10  # единственный проверенный тест обращения подтвердил


def test_nothing_verified_means_the_axis_is_not_measured(proto):
    """Все тесты умерли на грамматике запроса → свидетельств нет вовсе, балла тоже."""
    run = OneCRunResult(status="ok", passed=0, total=3, platform_error_tests=0, unverified_tests=3)
    band, detail = score_p(run, proto)
    assert band is None and detail["unmeasured"] == "query_never_parsed"


# ── плавная доля clean/total → ступенька P (достижимы {0,4,6,10}) ─────────────


@pytest.mark.parametrize(
    "total,bad,expected",
    [
        (5, 0, 10),  # все обращения к метаданным отработали (100% чистых)
        (4, 1, 6),  # 75% чистых → ≥0.5
        (4, 2, 6),  # 50% → ≥0.5
        (4, 3, 4),  # 25% → >0
        (4, 4, 0),  # 0% чистых → структура обращений вымышлена
    ],
)
def test_clean_share_to_band(proto, total, bad, expected):
    run = OneCRunResult(
        status="ok",
        passed=total - bad,
        total=total,
        platform_error_tests=bad,
        platform_errors=["Поле не найдено"] if bad else [],
    )
    band, detail = score_p(run, proto)
    assert band == expected
    assert detail["clean_share"] == round((total - bad) / total, 3)


# ── обработчик упал ДО тестов (total=0) ───────────────────────────────────────


def test_crashed_before_tests_with_metadata_error_is_zero(proto):
    """total=0, и упал он именно на метаданных → структура обращений вымышлена → 0."""
    run = OneCRunResult(
        status="ok",
        total=0,
        log="КЛИЕНТ_ИСКЛЮЧЕНИЕ: Объект не найден: Справочник.Контрагенты",
        platform_errors=["Объект не найден"],
    )
    band, detail = score_p(run, proto)
    assert band == 0 and detail["clean_share"] == 0.0


def test_crashed_before_tests_on_a_broken_query_is_not_zero(proto):
    """Тот же total=0, но упал на тексте запроса → ноль ставить не за что.

    Маркер «(Выполнить)» сработает и здесь, поэтому сырого его наличия мало: под ним
    лежит и кривой запрос, который по конституции идёт в ось M. Ветка обязана спрашивать
    тот же вердикт, что и разбор отдельных тестов, иначе граница осей рвётся.
    """
    run = OneCRunResult(
        status="ok",
        total=0,
        log=(
            "КЛИЕНТ_ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): "
            'Синтаксическая ошибка "ВЫБРАT"'
        ),
        platform_errors=["Ошибка при вызове метода контекста (Выполнить)"],
    )
    band, detail = score_p(run, proto)
    assert band is None and detail["unmeasured"] == "crashed_before_tests"


def test_crashed_before_tests_no_marker_not_measured(proto):
    """total=0 и платформенных маркеров нет → не измерено (None), а не 0."""
    band, detail = score_p(OneCRunResult(status="ok", total=0), proto)
    assert band is None and "обращений к метаданным не видно" in detail["reason"]
