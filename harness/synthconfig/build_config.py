"""Генератор синтетической конфигурации 1С (формат /LoadConfigFromFiles) из spec.

Авто-создание объектов из YAML-спеки — то, чего НЕ делают vrunner/gitsync/EDT-CLI
(они грузят/гоняют готовое). Формат откалиброван по реальной выгрузке (sample .dt):

 1. InternalInfo с <xr:GeneratedType>; GUID TypeId/ValueId — произвольные уникальные.
 2. Имена типов АНГЛИЙСКИЕ: CatalogRef.X, AccumulationRegisterRecordSet.X.
 3. Регистру накопления нужно 6 типов, включая RecordKey.
 4. Число: <v8:Type>xs:decimal</v8:Type> + объявленный xmlns:xs.
 5. Регистр требует документ-регистратор: в документе
    <RegisterRecords><xr:Item xsi:type="xr:MDObjectRef">AccumulationRegister.X</xr:Item></RegisterRecords>
 6. ConfigDumpInfo.xml в дереве не нужен (иначе манифест игнорирует новые файлы).

Пакет самодостаточен (только стандартная библиотека) — пригоден к выносу в отдельный
репозиторий. Никаких импортов из prism. См. README.md.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

HDR = ('<?xml version="1.0" encoding="UTF-8"?>\n<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" '
       'xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" '
       'xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xs="http://www.w3.org/2001/XMLSchema" '
       'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.20">\n')

CATALOG_TYPES = [("CatalogObject", "Object"), ("CatalogRef", "Ref"), ("CatalogSelection", "Selection"),
                 ("CatalogList", "List"), ("CatalogManager", "Manager")]
REG_TYPES = [("AccumulationRegisterRecord", "Record"), ("AccumulationRegisterManager", "Manager"),
             ("AccumulationRegisterSelection", "Selection"), ("AccumulationRegisterList", "List"),
             ("AccumulationRegisterRecordSet", "RecordSet"), ("AccumulationRegisterRecordKey", "RecordKey")]
DOC_TYPES = [("DocumentObject", "Object"), ("DocumentRef", "Ref"), ("DocumentSelection", "Selection"),
             ("DocumentList", "List"), ("DocumentManager", "Manager")]
# РегистрСведений: 7 типов, включая RecordManager (формат — по реальной выгрузке ЦеныНоменклатуры)
INFOREG_TYPES = [("InformationRegisterRecord", "Record"), ("InformationRegisterManager", "Manager"),
                 ("InformationRegisterSelection", "Selection"), ("InformationRegisterList", "List"),
                 ("InformationRegisterRecordSet", "RecordSet"), ("InformationRegisterRecordKey", "RecordKey"),
                 ("InformationRegisterRecordManager", "RecordManager")]


def _u() -> str:
    return str(uuid.uuid4())


def _gt(prefix: str, name: str, category: str) -> str:
    return (f'\t\t\t<xr:GeneratedType name="{prefix}.{name}" category="{category}">\n'
            f'\t\t\t\t<xr:TypeId>{_u()}</xr:TypeId>\n\t\t\t\t<xr:ValueId>{_u()}</xr:ValueId>\n'
            f'\t\t\t</xr:GeneratedType>\n')


def _syn(name: str, ind: str = "\t\t\t") -> str:
    return (f'{ind}<Synonym>\n{ind}\t<v8:item><v8:lang>ru</v8:lang>'
            f'<v8:content>{name}</v8:content></v8:item>\n{ind}</Synonym>\n')


def catalog_xml(name: str, hierarchical: bool = False, attributes: dict | None = None) -> str:
    """Справочник: иерархия (опц.) + произвольные реквизиты (опц.).

    attributes — как у документа: {Имя: {type, length, precision}}; реквизит группе
    тоже доступен (по умолчанию ДляЭлемента — достаточно для задач). Тип реквизита —
    через _type_xml (Число/Строка/Дата/СправочникСсылка/ДокументСсылка).
    """
    types = "".join(_gt(p, name, c) for p, c in CATALOG_TYPES)
    hier = ('\t\t\t<Hierarchical>true</Hierarchical>\n'
            '\t\t\t<HierarchyType>HierarchyFoldersAndItems</HierarchyType>\n'
            if hierarchical else '\t\t\t<Hierarchical>false</Hierarchical>\n')
    attrs = "".join(_field("Attribute", n, s) for n, s in (attributes or {}).items())
    child_block = f'\t\t<ChildObjects>\n{attrs}\t\t</ChildObjects>\n' if attrs else '\t\t<ChildObjects/>\n'
    return (HDR + f'\t<Catalog uuid="{_u()}">\n\t\t<InternalInfo>\n{types}\t\t</InternalInfo>\n\t\t<Properties>\n'
            f'\t\t\t<Name>{name}</Name>\n{_syn(name)}{hier}'
            '\t\t\t<CodeLength>9</CodeLength>\n\t\t\t<DescriptionLength>50</DescriptionLength>\n'
            '\t\t\t<CodeType>String</CodeType>\n\t\t</Properties>\n' + child_block + '\t</Catalog>\n</MetaDataObject>\n')


def _type_xml(spec: dict, ind: str = "\t\t\t\t") -> str:
    """Тип реквизита/измерения/ресурса из YAML-спеки.

    Поддержано (то, что нужно B1–B5): СправочникСсылка.X / ДокументСсылка.X,
    Число {length, precision}, Строка {length}, Дата.
    """
    t = spec.get("type", "Число")
    i2 = ind + "\t"
    if t.startswith("СправочникСсылка."):
        inner = f"{i2}<v8:Type>cfg:CatalogRef.{t.split('.', 1)[1]}</v8:Type>\n"
    elif t.startswith("ДокументСсылка."):
        inner = f"{i2}<v8:Type>cfg:DocumentRef.{t.split('.', 1)[1]}</v8:Type>\n"
    elif t == "Число":
        inner = (f"{i2}<v8:Type>xs:decimal</v8:Type>\n{i2}<v8:NumberQualifiers>\n"
                 f"{i2}\t<v8:Digits>{spec.get('length', 15)}</v8:Digits>\n"
                 f"{i2}\t<v8:FractionDigits>{spec.get('precision', 0)}</v8:FractionDigits>\n"
                 f"{i2}\t<v8:AllowedSign>Any</v8:AllowedSign>\n{i2}</v8:NumberQualifiers>\n")
    elif t == "Строка":
        inner = (f"{i2}<v8:Type>xs:string</v8:Type>\n{i2}<v8:StringQualifiers>\n"
                 f"{i2}\t<v8:Length>{spec.get('length', 100)}</v8:Length>\n"
                 f"{i2}\t<v8:AllowedLength>Variable</v8:AllowedLength>\n{i2}</v8:StringQualifiers>\n")
    elif t == "Дата":
        inner = (f"{i2}<v8:Type>xs:dateTime</v8:Type>\n{i2}<v8:DateQualifiers>\n"
                 f"{i2}\t<v8:DateFractions>DateTime</v8:DateFractions>\n{i2}</v8:DateQualifiers>\n")
    else:
        raise ValueError(f"неподдерживаемый тип в спеке: {t}")
    return f"{ind}<Type>\n{inner}{ind}</Type>\n"


def _field(tag: str, name: str, type_spec: dict, ind: str = "\t\t\t") -> str:
    """Реквизит/Измерение/Ресурс: <tag uuid><Properties><Name/Synonym/Type></Properties></tag>."""
    i1, i2 = ind + "\t", ind + "\t\t"
    return (f'{ind}<{tag} uuid="{_u()}">\n{i1}<Properties>\n{i2}<Name>{name}</Name>\n'
            + _syn(name, i2) + _type_xml(type_spec, i2)
            + f'{i1}</Properties>\n{ind}</{tag}>\n')


def accumreg_xml(name: str, dimensions: dict, resources: dict,
                 register_type: str = "Balance") -> str:
    """register_type: Balance (остатки, ВТ .Остатки/.ОстаткиИОбороты) | Turnovers (обороты).

    Поля — через _field/_type_xml: измерение может быть и СправочникСсылка, и
    ДокументСсылка (партия = документ поступления в FIFO-задачах).
    """
    types = "".join(_gt(p, name, c) for p, c in REG_TYPES)
    childs = "".join(_field("Resource", n, {"type": "Число", **s}) for n, s in resources.items())
    childs += "".join(_field("Dimension", n, s) for n, s in dimensions.items())
    return (HDR + f'\t<AccumulationRegister uuid="{_u()}">\n\t\t<InternalInfo>\n{types}\t\t</InternalInfo>\n'
            f'\t\t<Properties>\n\t\t\t<Name>{name}</Name>\n{_syn(name)}'
            f'\t\t\t<RegisterType>{register_type}</RegisterType>\n\t\t</Properties>\n'
            f'\t\t<ChildObjects>\n{childs}\t\t</ChildObjects>\n\t</AccumulationRegister>\n</MetaDataObject>\n')


def information_register_xml(name: str, dimensions: dict, resources: dict,
                             periodicity: str = "Day") -> str:
    """Независимый периодический РегистрСведений (СрезПоследних без регистратора).

    periodicity: Day/Month/Year/Second; для непериодического — Nonperiodical
    (но тогда СрезПоследних недоступен).
    """
    types = "".join(_gt(p, name, c) for p, c in INFOREG_TYPES)
    childs = "".join(_field("Resource", n, s) for n, s in resources.items())
    childs += "".join(_field("Dimension", n, s) for n, s in dimensions.items())
    return (HDR + f'\t<InformationRegister uuid="{_u()}">\n\t\t<InternalInfo>\n{types}\t\t</InternalInfo>\n'
            f'\t\t<Properties>\n\t\t\t<Name>{name}</Name>\n{_syn(name)}'
            f'\t\t\t<InformationRegisterPeriodicity>{periodicity}</InformationRegisterPeriodicity>\n'
            '\t\t\t<WriteMode>Independent</WriteMode>\n'
            '\t\t\t<MainFilterOnPeriod>false</MainFilterOnPeriod>\n'
            '\t\t</Properties>\n'
            f'\t\t<ChildObjects>\n{childs}\t\t</ChildObjects>\n\t</InformationRegister>\n</MetaDataObject>\n')


def _tabular_section_xml(doc_name: str, ts_name: str, attributes: dict) -> str:
    """Табличная часть документа: свой InternalInfo (TabularSection + Row) + атрибуты."""
    types = (f'\t\t\t\t<xr:GeneratedType name="DocumentTabularSection.{doc_name}.{ts_name}" category="TabularSection">\n'
             f'\t\t\t\t\t<xr:TypeId>{_u()}</xr:TypeId>\n\t\t\t\t\t<xr:ValueId>{_u()}</xr:ValueId>\n'
             f'\t\t\t\t</xr:GeneratedType>\n'
             f'\t\t\t\t<xr:GeneratedType name="DocumentTabularSectionRow.{doc_name}.{ts_name}" category="TabularSectionRow">\n'
             f'\t\t\t\t\t<xr:TypeId>{_u()}</xr:TypeId>\n\t\t\t\t\t<xr:ValueId>{_u()}</xr:ValueId>\n'
             f'\t\t\t\t</xr:GeneratedType>\n')
    attrs = "".join(_field("Attribute", n, s, "\t\t\t\t") for n, s in attributes.items())
    return (f'\t\t\t<TabularSection uuid="{_u()}">\n\t\t\t\t<InternalInfo>\n{types}\t\t\t\t</InternalInfo>\n'
            f'\t\t\t\t<Properties>\n\t\t\t\t\t<Name>{ts_name}</Name>\n{_syn(ts_name, chr(9) * 5)}'
            f'\t\t\t\t</Properties>\n'
            f'\t\t\t\t<ChildObjects>\n{attrs}\t\t\t\t</ChildObjects>\n\t\t\t</TabularSection>\n')


def document_xml(name: str, registers: list[str] | None = None, attributes: dict | None = None,
                 tabular_sections: dict | None = None) -> str:
    """Документ: регистратор (RegisterRecords) + шапочные реквизиты + табличные части."""
    types = "".join(_gt(p, name, c) for p, c in DOC_TYPES)
    items = "".join(f'\t\t\t\t<xr:Item xsi:type="xr:MDObjectRef">AccumulationRegister.{r}</xr:Item>\n'
                    for r in (registers or []))
    reg_block = (f'\t\t\t<RegisterRecords>\n{items}\t\t\t</RegisterRecords>\n'
                 if items else '\t\t\t<RegisterRecords/>\n')
    childs = "".join(_field("Attribute", n, s) for n, s in (attributes or {}).items())
    childs += "".join(_tabular_section_xml(name, ts, spec.get("attributes", {}))
                      for ts, spec in (tabular_sections or {}).items())
    child_block = f'\t\t<ChildObjects>\n{childs}\t\t</ChildObjects>\n' if childs else '\t\t<ChildObjects/>\n'
    return (HDR + f'\t<Document uuid="{_u()}">\n\t\t<InternalInfo>\n{types}\t\t</InternalInfo>\n\t\t<Properties>\n'
            f'\t\t\t<Name>{name}</Name>\n{_syn(name)}'
            '\t\t\t<NumberType>String</NumberType>\n\t\t\t<NumberLength>11</NumberLength>\n'
            '\t\t\t<NumberAllowedLength>Variable</NumberAllowedLength>\n'
            '\t\t\t<Posting>Allow</Posting>\n\t\t\t<RealTimePosting>Deny</RealTimePosting>\n'
            '\t\t\t<RegisterRecordsDeletion>AutoDeleteOff</RegisterRecordsDeletion>\n'
            '\t\t\t<RegisterRecordsWritingOnPost>WriteSelected</RegisterRecordsWritingOnPost>\n'
            + reg_block +
            '\t\t</Properties>\n' + child_block + '\t</Document>\n</MetaDataObject>\n')


def build(spec: dict, empty_cfg: Path, out_cfg: Path) -> None:
    """Собрать дерево LoadConfigFromFiles из spec поверх выгрузки пустой конфы.

    empty_cfg — выгрузка ПУСТОЙ конфигурации (DumpConfigToFiles), не хранится в git
    (воссоздаётся платформой); out_cfg — результат, готовый к LoadConfigFromFiles.
    """
    import shutil
    if out_cfg.exists():
        shutil.rmtree(out_cfg)
    shutil.copytree(empty_cfg, out_cfg)
    (out_cfg / "ConfigDumpInfo.xml").unlink(missing_ok=True)

    child = []
    for folder in ("Catalogs", "Documents", "AccumulationRegisters", "InformationRegisters"):
        (out_cfg / folder).mkdir(exist_ok=True)

    for nm, cat in spec.get("catalogs", {}).items():
        (out_cfg / "Catalogs" / f"{nm}.xml").write_text(
            catalog_xml(nm, cat.get("hierarchical", False), cat.get("attributes", {})), encoding="utf-8")
        child.append(f"\t\t\t<Catalog>{nm}</Catalog>")
    for nm, doc in spec.get("documents", {}).items():
        (out_cfg / "Documents" / f"{nm}.xml").write_text(
            document_xml(nm, doc.get("registers", []), doc.get("attributes", {}),
                         doc.get("tabular_sections", {})), encoding="utf-8")
        child.append(f"\t\t\t<Document>{nm}</Document>")
    for nm, reg in spec.get("accumulation_registers", {}).items():
        (out_cfg / "AccumulationRegisters" / f"{nm}.xml").write_text(
            accumreg_xml(nm, reg.get("dimensions", {}), reg.get("resources", {}),
                         reg.get("register_type", "Balance")), encoding="utf-8")
        child.append(f"\t\t\t<AccumulationRegister>{nm}</AccumulationRegister>")
    for nm, reg in spec.get("information_registers", {}).items():
        (out_cfg / "InformationRegisters" / f"{nm}.xml").write_text(
            information_register_xml(nm, reg.get("dimensions", {}), reg.get("resources", {}),
                                     reg.get("periodicity", "Day")), encoding="utf-8")
        child.append(f"\t\t\t<InformationRegister>{nm}</InformationRegister>")

    conf = out_cfg / "Configuration.xml"
    s = conf.read_text(encoding="utf-8-sig")
    inject = "\t\t\t<Language>Русский</Language>\n" + "\n".join(child) + "\n"
    s = re.sub(r"\t\t\t<Language>Русский</Language>\n", inject, s)
    conf.write_text(s if s.startswith("﻿") else "﻿" + s, encoding="utf-8")
