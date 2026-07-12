"""Сборка прогонной конфигурации B-задачи: база из описания + добавление модулей прогона.

Выход — дерево /LoadConfigFromFiles:
  объекты задачи (config_spec.yaml → synthconfig)
  + общий модуль «КодКандидата»  (текст кандидата; ServerCall=false)
  + общий модуль «Тесты»         (фикстуры из fixtures.yaml + проверки tests.bsl; ServerCall=true)
  + Ext/ManagedApplicationModule.bsl — триггер прогона (проверен исполнением):
      ПараметрЗапуска содержит «ПрогонТеста» → через ОбработчикОжидания выполнить
      Тесты.ПрогнатьТест(), записать результат в файл, завершить работу.

Грабли платформы (зафиксированы прогоном): модуль с ServerCall нельзя звать с сервера —
поэтому кандидат ServerCall=false, раннер-модуль ServerCall=true; после загрузки конфы
обязателен /UpdateDBCfg.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import yaml

from harness.synthconfig import build as build_base_config

from .fixtures_gen import generate_fixtures_module

BOM = "﻿"

_CM_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core" '
    'xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.20">\n'
    '\t<CommonModule uuid="{uid}">\n\t\t<Properties>\n\t\t\t<Name>{name}</Name>\n'
    "\t\t\t<Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>{name}</v8:content></v8:item></Synonym>\n"
    "\t\t\t<Global>false</Global>\n\t\t\t<ClientManagedApplication>false</ClientManagedApplication>\n"
    "\t\t\t<Server>true</Server>\n\t\t\t<ExternalConnection>false</ExternalConnection>\n"
    "\t\t\t<ClientOrdinaryApplication>false</ClientOrdinaryApplication>\n"
    "\t\t\t<ServerCall>{servercall}</ServerCall>\n\t\t\t<Privileged>true</Privileged>\n"
    "\t\t\t<ReturnValuesReuse>DontUse</ReturnValuesReuse>\n\t\t</Properties>\n\t</CommonModule>\n"
    "</MetaDataObject>\n"
)

_HANDLER = """Процедура ПриНачалеРаботыСистемы()
\tЕсли СтрНайти(ПараметрЗапуска, "ПрогонТеста") > 0 Тогда
\t\tПодключитьОбработчикОжидания("ПрогонТестаОбработчик", 1, Истина);
\tКонецЕсли;
КонецПроцедуры

Процедура ПрогонТестаОбработчик() Экспорт
\tПопытка
\t\tРезультат = Тесты.ПрогнатьТест();
\tИсключение
\t\tРезультат = "КЛИЕНТ_ИСКЛЮЧЕНИЕ: " + ОписаниеОшибки();
\tКонецПопытки;
\tТекст = Новый ТекстовыйДокумент;
\tТекст.УстановитьТекст(Результат);
\tТекст.Записать("{result_path}");
\tЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры
"""


def _add_common_module(out_cfg: Path, name: str, body: str, servercall: bool) -> None:
    (out_cfg / "CommonModules").mkdir(exist_ok=True)
    (out_cfg / "CommonModules" / f"{name}.xml").write_text(
        _CM_XML.format(uid=uuid.uuid4(), name=name, servercall=str(servercall).lower()),
        encoding="utf-8",
    )
    ext = out_cfg / "CommonModules" / name / "Ext"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "Module.bsl").write_text(BOM + body, encoding="utf-8")


def ensure_exported(code: str, entry: str) -> str:
    """Дописать «Экспорт» точке входа, если его нет.

    Точку входа тесты зовут из ДРУГОГО модуля (Тесты → КодКандидата.<entry>), а в 1С метод
    общего модуля виден снаружи только с «Экспорт». Промпт про это не говорит — модель не знает,
    что её код идёт «библиотекой» под тесты. Поэтому меряем ЛОГИКУ, а не угаданную конвенцию вызова:
    рабочая функция без «Экспорт» больше не проваливается на «Метод объекта не обнаружен».
    """
    pat = re.compile(
        r"(?im)^([ \t]*(?:Функция|Процедура)[ \t]+"
        + re.escape(entry)
        + r"[ \t]*\([^)]*\))([ \t]*)(Экспорт\b)?"
    )

    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(3) else m.group(1) + " Экспорт"

    new, n = pat.subn(repl, code, count=1)
    return new if n else code


def assemble_run_config(
    task_dir: Path,
    candidate_code: str,
    entry: str,
    empty_cfg: Path,
    out_cfg: Path,
    result_path: str = "/work/result.txt",
) -> None:
    """Собрать готовую к загрузке конфигурацию прогона одного кандидата."""
    spec = yaml.safe_load((task_dir / "config_spec.yaml").read_text(encoding="utf-8"))
    build_base_config(spec, empty_cfg, out_cfg)

    # кандидат: логические ошибки ловит прогон, но точку входа авто-экспортируем — чтобы её
    # вообще можно было позвать из модуля Тесты (промпт про «Экспорт» умалчивает, см. ensure_exported)
    _add_common_module(
        out_cfg, "КодКандидата", ensure_exported(candidate_code, entry), servercall=False
    )

    # тесты: сгенерённые фикстуры + проверки задачи с подставленным именем функции
    fixtures = yaml.safe_load((task_dir / "fixtures.yaml").read_text(encoding="utf-8"))
    checks = (task_dir / "tests.bsl").read_text(encoding="utf-8-sig").replace("{{ENTRY}}", entry)
    _add_common_module(
        out_cfg, "Тесты", generate_fixtures_module(fixtures) + "\n" + checks, servercall=True
    )

    # триггер прогона
    ext = out_cfg / "Ext"
    ext.mkdir(exist_ok=True)
    (ext / "ManagedApplicationModule.bsl").write_text(
        BOM + _HANDLER.format(result_path=result_path), encoding="utf-8"
    )

    # объявить общие модули в Configuration.xml
    conf = out_cfg / "Configuration.xml"
    s = conf.read_text(encoding="utf-8-sig")
    anchor = "\t\t\t<Language>Русский</Language>\n"
    decl = (
        anchor
        + "\t\t\t<CommonModule>КодКандидата</CommonModule>\n"
        + "\t\t\t<CommonModule>Тесты</CommonModule>\n"
    )
    if anchor not in s:
        raise RuntimeError("Configuration.xml: не найден якорь <Language>Русский</Language>")
    conf.write_text(BOM + s.replace(anchor, decl, 1), encoding="utf-8")
