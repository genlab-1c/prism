"""Тесты генератора синтетической конфигурации — офлайн (без 1С/Docker).

Покрывают расширения Tier 1: булев и составной тип, табличные части справочников,
перечисления, константы — на трёх слоях: XML схемы (build_config), BSL-фикстуры
(fixtures_gen) и текст схемы для модели (synth.render_schema). Корректность XML
относительно реального LoadConfigFromFiles проверяется уже исполнением задачи в 1С
(prism check --runner docker) — здесь гейтятся структура и проводка значений.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET

from harness.execute.onec.fixtures_gen import generate_fixtures_module
from harness.synthconfig import (
    accumreg_xml,
    build,
    catalog_xml,
    constant_xml,
    document_xml,
    enum_xml,
    information_register_xml,
    predefined_xml,
    render_schema,
)
from harness.synthconfig.build_config import _type_xml

# ── well-formedness: всякий объект — валидный XML (префиксы из HDR объявлены) ──


def test_all_object_xml_is_well_formed():
    """Структурная корректность (не семантика 1С): парсится ElementTree без ошибок."""
    samples = [
        enum_xml("СтатусыЗаказов", ["Новый", "Выполнен"]),
        constant_xml("БазоваяВалюта", {"type": "СправочникСсылка.Валюты"}),
        catalog_xml(
            "Спецификации",
            hierarchical=True,
            attributes={
                "Услуга": {"type": "Булево"},
                "Получатель": {"type": ["СправочникСсылка.А", "СправочникСсылка.Б"]},
            },
            tabular_sections={"Материалы": {"attributes": {"Кол": {"type": "Число"}}}},
        ),
        document_xml(
            "Платёж",
            registers=["Взаиморасчёты"],
            attributes={"Сумма": {"type": "Число", "length": 15, "precision": 2}},
            tabular_sections={"Строки": {"attributes": {"Товар": {"type": "СправочникСсылка.Н"}}}},
        ),
        accumreg_xml(
            "Взаиморасчёты",
            {"Контрагент": {"type": "СправочникСсылка.К"}},
            {"Сумма": {"length": 15, "precision": 2}},
        ),
    ]
    for xml in samples:
        ET.fromstring(xml)  # бросит ParseError при кривой вложенности/незакрытом теге


# ── типы: булево / составной / ссылка на перечисление ────────────────────────


def test_boolean_type():
    xml = catalog_xml("Номенклатура", attributes={"Услуга": {"type": "Булево"}})
    assert "<v8:Type>xs:boolean</v8:Type>" in xml


def test_enum_ref_type():
    xml = _type_xml({"type": "ПеречислениеСсылка.СтатусыЗаказов"})
    assert "<v8:Type>cfg:EnumRef.СтатусыЗаказов</v8:Type>" in xml


def test_composite_type_two_members_one_wrapper():
    """Составной тип: один <Type> с несколькими <v8:Type> (под ВЫРАЗИТЬ ... КАК ...)."""
    xml = _type_xml({"type": ["СправочникСсылка.ФизЛица", "СправочникСсылка.ЮрЛица"]})
    assert "cfg:CatalogRef.ФизЛица" in xml and "cfg:CatalogRef.ЮрЛица" in xml
    assert xml.count("<Type>") == 1  # одна обёртка
    assert xml.count("<v8:Type>") == 2  # два члена


def test_unknown_type_raises():
    import pytest

    with pytest.raises(ValueError):
        _type_xml({"type": "ХранилищеЗначения"})


# ── табличные части справочника ──────────────────────────────────────────────


def test_catalog_tabular_section():
    xml = catalog_xml(
        "Спецификации",
        tabular_sections={
            "Материалы": {
                "attributes": {
                    "Материал": {"type": "СправочникСсылка.Номенклатура"},
                    "Количество": {"type": "Число", "length": 10, "precision": 3},
                }
            }
        },
    )
    assert 'name="CatalogTabularSection.Спецификации.Материалы"' in xml
    assert 'name="CatalogTabularSectionRow.Спецификации.Материалы"' in xml
    assert "<Name>Материал</Name>" in xml and "<Name>Количество</Name>" in xml


# ── перечисления ─────────────────────────────────────────────────────────────


def test_enum_xml_values_and_types():
    xml = enum_xml("СтатусыЗаказов", ["Новый", "ВРаботе", "Выполнен"])
    assert "<Enum uuid=" in xml
    assert 'name="EnumRef.СтатусыЗаказов" category="Ref"' in xml
    for v in ("Новый", "ВРаботе", "Выполнен"):
        assert f"<Name>{v}</Name>" in xml


# ── константы ────────────────────────────────────────────────────────────────


def test_constant_xml():
    xml = constant_xml("БазоваяВалюта", {"type": "СправочникСсылка.Валюты"})
    assert "<Constant uuid=" in xml
    assert "<Name>БазоваяВалюта</Name>" in xml
    assert "<v8:Type>cfg:CatalogRef.Валюты</v8:Type>" in xml


# ── подчинённый регистр сведений (write_mode RecorderSubordinate) ────────────


def test_information_register_write_mode():
    indep = information_register_xml(
        "Цены", {"Н": {"type": "СправочникСсылка.Номенклатура"}}, {"Цена": {"type": "Число"}}
    )
    assert "<WriteMode>Independent</WriteMode>" in indep
    sub = information_register_xml(
        "Цены",
        {"Н": {"type": "СправочникСсылка.Номенклатура"}},
        {"Цена": {"type": "Число"}},
        write_mode="RecorderSubordinate",
    )
    assert "<WriteMode>RecorderSubordinate</WriteMode>" in sub


def test_document_records_information_register():
    xml = document_xml("УстановкаЦен", info_registers=["ЦеныДокументом"])
    assert '<xr:Item xsi:type="xr:MDObjectRef">InformationRegister.ЦеныДокументом</xr:Item>' in xml


def test_fixtures_subordinate_info_register_via_registrar():
    bsl = generate_fixtures_module(
        {
            "catalogs": {"Номенклатура": [{"ref": "Т1", "Наименование": "Товар А"}]},
            "info_register_records": {
                "ЦеныДокументом": {
                    "registrar": "УстановкаЦен",
                    "records": [
                        {"Период": datetime.date(2026, 1, 1), "Номенклатура": "Т1", "Цена": 100}
                    ],
                }
            },
        }
    )
    assert "Документы.УстановкаЦен.СоздатьДокумент();" in bsl
    assert "РегистрыСведений.ЦеныДокументом.СоздатьНаборЗаписей();" in bsl
    assert "Набор.Отбор.Регистратор.Установить(Док.Ссылка);" in bsl
    assert "З.Цена = 100;" in bsl
    assert "ВидДвижения" not in bsl  # у РС вида движения нет


def test_render_subordinate_info_register():
    spec = {
        "information_registers": {
            "Цены": {
                "write_mode": "RecorderSubordinate",
                "dimensions": {"Н": {"type": "СправочникСсылка.Номенклатура"}},
                "resources": {"Цена": {"type": "Число"}},
            }
        }
    }
    assert "подчинён регистратору" in render_schema(spec)


# ── предопределённые элементы (частично: XML грузится; runtime-инициализация — TODO) ──


def test_predefined_xml_format():
    xml = predefined_xml(["Основной", {"name": "Услуги", "folder": True}])
    assert 'version="2.20"' in xml  # обязательно — иначе несовпадение формата
    assert "<Name>Основной</Name>" in xml
    assert "<Name>Услуги</Name>" in xml and "<IsFolder>true</IsFolder>" in xml
    ET.fromstring(xml)  # well-formed


# ── build(): дерево + инъекция в Configuration.xml ───────────────────────────

_EMPTY_CONF = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<MetaDataObject>\n\t<Configuration>\n'
    "\t\t<ChildObjects>\n\t\t\t<Language>Русский</Language>\n"
    "\t\t</ChildObjects>\n\t</Configuration>\n</MetaDataObject>\n"
)


def test_build_writes_objects_and_injects_children(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "Configuration.xml").write_text(_EMPTY_CONF, encoding="utf-8")
    out = tmp_path / "out"

    spec = {
        "constants": {"БазоваяВалюта": {"type": "СправочникСсылка.Валюты"}},
        "enums": {"СтатусыЗаказов": ["Новый", "Выполнен"]},
        "catalogs": {"Валюты": {}},
    }
    build(spec, empty_cfg=empty, out_cfg=out)

    assert (out / "Constants" / "БазоваяВалюта.xml").exists()
    assert (out / "Enums" / "СтатусыЗаказов.xml").exists()
    assert (out / "Catalogs" / "Валюты.xml").exists()
    conf = (out / "Configuration.xml").read_text(encoding="utf-8-sig")
    assert "<Constant>БазоваяВалюта</Constant>" in conf
    assert "<Enum>СтатусыЗаказов</Enum>" in conf
    assert "<Catalog>Валюты</Catalog>" in conf
    # канонический порядок: Константа раньше Справочника, Перечисление позже
    assert conf.index("<Constant>") < conf.index("<Catalog>") < conf.index("<Enum>")


# ── фикстуры: проводка значений в BSL ────────────────────────────────────────


def test_fixtures_boolean():
    bsl = generate_fixtures_module(
        {
            "catalogs": {
                "Ном": [
                    {"ref": "Н1", "Наименование": "Услуга связи", "Услуга": True},
                    {"ref": "Н2", "Наименование": "Товар", "Услуга": False},
                ]
            }
        }
    )
    assert "Об.Услуга = Истина;" in bsl
    assert "Об.Услуга = Ложь;" in bsl


def test_fixtures_enum_passthrough():
    bsl = generate_fixtures_module(
        {
            "catalogs": {
                "Заказы": [
                    {
                        "ref": "З1",
                        "Наименование": "Заказ 1",
                        "Статус": "Перечисления.СтатусыЗаказов.Выполнен",
                    }
                ]
            }
        }
    )
    assert "Об.Статус = Перечисления.СтатусыЗаказов.Выполнен;" in bsl
    assert '"Перечисления' not in bsl  # НЕ как строка


def test_fixtures_catalog_tabular_section():
    bsl = generate_fixtures_module(
        {
            "catalogs": {
                "Спецификации": [
                    {
                        "ref": "С1",
                        "Наименование": "Изделие А",
                        "Материалы": [
                            {"Материал": "М1", "Количество": 2},
                            {"Материал": "М2", "Количество": 5},
                        ],
                    }
                ]
            }
        }
    )
    assert "Об.Материалы.Добавить();" in bsl
    assert "Стр.Количество = 2;" in bsl and "Стр.Количество = 5;" in bsl


def test_fixtures_constants():
    bsl = generate_fixtures_module({"constants": {"СтавкаНДС": 20, "Город": "Москва"}})
    assert "Константы.СтавкаНДС.Установить(20);" in bsl
    assert 'Константы.Город.Установить("Москва");' in bsl


# ── render_schema: контекст для модели ───────────────────────────────────────


def test_render_constants_enums_and_catalog_ts():
    spec = {
        "constants": {"БазоваяВалюта": {"type": "СправочникСсылка.Валюты"}},
        "enums": {"СтатусыЗаказов": ["Новый", "Выполнен"]},
        "catalogs": {
            "Спецификации": {
                "tabular_sections": {
                    "Материалы": {
                        "attributes": {
                            "Материал": {"type": "СправочникСсылка.Номенклатура"},
                            "Количество": {"type": "Число", "length": 10, "precision": 3},
                        }
                    }
                }
            }
        },
    }
    text = render_schema(spec)
    assert "Константы:" in text and "Константа.БазоваяВалюта" in text
    assert "Перечисление.СтатусыЗаказов: Новый, Выполнен" in text
    assert "Табличная часть Материалы:" in text and "Количество" in text


def test_render_composite_label():
    spec = {
        "catalogs": {
            "Платежи": {
                "attributes": {
                    "Получатель": {"type": ["СправочникСсылка.ФизЛица", "СправочникСсылка.ЮрЛица"]}
                }
            }
        }
    }
    assert "составной (" in render_schema(spec)
