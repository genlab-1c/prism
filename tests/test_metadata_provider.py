"""Тесты SpecMetadataProvider — офлайн, на синтетическом спеке (без 1С и сети).

Проверяем: набор инструментов, список «Тип.Имя» (+фильтр по типу), поиск по имени,
структуру объекта (регистр/документ с ТЧ/справочник), разрешение «Тип.Имя» и бар-имени,
ненайденный объект и неизвестный инструмент.
"""

from __future__ import annotations

import pytest

from harness.generate.context import SpecMetadataProvider

SPEC = {
    "catalogs": {
        "Номенклатура": {"hierarchical": True},
        "Склады": {"hierarchical": False},
    },
    "documents": {
        "РеализацияТоваров": {
            "tabular_sections": {"Товары": {"attributes": {
                "Номенклатура": {"type": "СправочникСсылка.Номенклатура"},
                "Цена": {"type": "Число", "length": 15, "precision": 2}}}},
            "registers": ["ТоварыНаСкладах"]},
    },
    "accumulation_registers": {
        "ТоварыНаСкладах": {
            "register_type": "Balance",
            "dimensions": {"Склад": {"type": "СправочникСсылка.Склады"},
                           "Номенклатура": {"type": "СправочникСсылка.Номенклатура"}},
            "resources": {"ВНаличии": {"type": "Число", "length": 15, "precision": 3}}},
    },
    "information_registers": {
        "ЦеныНоменклатуры": {
            "periodicity": "Day",
            "dimensions": {"Номенклатура": {"type": "СправочникСсылка.Номенклатура"}},
            "resources": {"Цена": {"type": "Число", "length": 15, "precision": 2}}},
    },
}


@pytest.fixture
def provider():
    return SpecMetadataProvider(SPEC)


def test_tools_shape(provider):
    names = {t["function"]["name"] for t in provider.tools()}
    assert names == {"list_objects", "search_objects", "get_object_structure"}
    # у list_objects enum типов перечислен
    lo = next(t for t in provider.tools() if t["function"]["name"] == "list_objects")
    assert "РегистрНакопления" in lo["function"]["parameters"]["properties"]["kind"]["enum"]


def test_list_all_and_filtered(provider):
    all_objs = provider.call("list_objects", {}).splitlines()
    assert "Справочник.Номенклатура" in all_objs
    assert "РегистрНакопления.ТоварыНаСкладах" in all_objs
    assert "РегистрСведений.ЦеныНоменклатуры" in all_objs
    assert len(all_objs) == 5                       # 2 спр + 1 док + 1 РН + 1 РС

    only_reg = provider.call("list_objects", {"kind": "РегистрНакопления"}).splitlines()
    assert only_reg == ["РегистрНакопления.ТоварыНаСкладах"]


def test_search_case_insensitive(provider):
    hits = provider.call("search_objects", {"query": "товар"}).splitlines()
    assert "РегистрНакопления.ТоварыНаСкладах" in hits
    assert "Документ.РеализацияТоваров" in hits
    assert provider.call("search_objects", {"query": "ничегонет"}).startswith("(ничего")


def test_structure_register_with_dims_and_resources(provider):
    s = provider.call("get_object_structure", {"name": "РегистрНакопления.ТоварыНаСкладах"})
    assert "вид: остатки" in s
    assert "Склад (СправочникСсылка.Склады)" in s
    assert "ВНаличии (Число 15.3)" in s


def test_structure_document_with_tabular_section(provider):
    s = provider.call("get_object_structure", {"name": "РеализацияТоваров"})   # бар-имя
    assert "табличная часть Товары" in s
    assert "Цена (Число 15.2)" in s
    assert "движения по регистрам: ТоварыНаСкладах" in s


def test_structure_catalog_hierarchy(provider):
    assert "иерархический" in provider.call("get_object_structure", {"name": "Номенклатура"})
    assert "не иерархический" in provider.call("get_object_structure", {"name": "Склады"})


def test_unknown_object_and_tool(provider):
    assert "не найден" in provider.call("get_object_structure", {"name": "ВымышленныйРегистр"})
    assert "неизвестный инструмент" in provider.call("delete_everything", {})
