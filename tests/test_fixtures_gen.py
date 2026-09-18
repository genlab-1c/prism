"""Тесты генератора фикстур (harness/execute/onec/fixtures_gen.py).

Фикстуры — это УСЛОВИЕ задачи, записанное в базу. Ошибка здесь не видна ни в одном балле:
она выглядит как провал модели. Поэтому обязательность даты движения закреплена тестом.
"""

from __future__ import annotations

import glob

import pytest
import yaml

from harness.execute.onec.fixtures_gen import generate_fixtures_module


def _fixtures(period: str | None) -> dict:
    rec = {"Склад": "Основной", "Номенклатура": "Товар1", "ВНаличии": 100}
    if period:
        rec = {"Период": period, **rec}
    return {
        "catalogs": {"Склады": [{"ref": "Основной", "Наименование": "Осн"}]},
        "register_records": {"ТоварыНаСкладах": {"registrar": "ВводОстатков", "records": [rec]}},
    }


def test_movement_without_a_date_is_rejected():
    """Без явной даты движение попадало на момент прогона — и срез остатков его не видел.

    Виртуальная таблица остатков границу НЕ включает. Решение, честно передавшее текущую
    дату параметром момента, получало ПУСТОЙ регистр и теряло все тесты: падал стенд, а не
    код (поймано на B14, латентно жило в B1). Исход вдобавок зависел от того, разошлись ли
    запись фикстуры и запрос кандидата на секунду. Молчаливый дефолт недопустим.
    """
    with pytest.raises(ValueError, match="не задан Период"):
        generate_fixtures_module(_fixtures(None))


def test_movement_with_an_explicit_date_is_generated():
    code = generate_fixtures_module(_fixtures("2026-01-15"))
    assert "ТекущаяДата()" not in code  # дата берётся из фикстуры, а не из часов машины
    assert "2026" in code


@pytest.mark.parametrize("path", sorted(glob.glob("tasks/category_b/*/fixtures.yaml")))
def test_every_task_fixture_builds(path):
    """Гейт на банк: ни одна задача не должна полагаться на молчаливую дату."""
    generate_fixtures_module(yaml.safe_load(open(path, encoding="utf-8")))
