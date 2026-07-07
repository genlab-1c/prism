"""Генерация BSL-фикстур из fixtures.yaml задачи категории B.

fixtures.yaml (декларативно) → текст BSL-процедур для модуля «Тесты»:

    СоздатьФикстуры()  — создаёт элементы/группы справочников, движения регистров
                         накопления и записи регистров сведений
    Спр(Справочник, Наименование) — поиск ссылки (используется и проверками задачи)

Приёмы — проверенные прогоном:
 - элемент справочника: служебные ключи ref/Наименование/isFolder/parent, остальные
   ключи → РЕКВИЗИТЫ справочника (config_spec.catalogs.<имя>.attributes), напр. ИНН,
   Коэффициент; ключ со значением-СПИСКОМ → строки табличной части справочника
   (config_spec.catalogs.<имя>.tabular_sections), напр. ТЧ Материалы спецификации;
 - булево: true/false в YAML → Истина/Ложь; перечисление: строка вида
   "Перечисления.<Имя>.<Значение>" пробрасывается как ссылка перечисления;
 - константы: блок constants (имя → значение) → Константы.<Имя>.Установить(...);
 - подчинённый справочник: ключ owner у элемента (ref владельца, объявлен раньше) →
   Об.Владелец = ...; виды субконто (элементы ПВХ): блок characteristics (ref/
   Наименование/ТипЗначения) → СоздатьЭлемент с ОписаниеТипов;
 - счета: блок accounts[ПланСчетов] (ref/Код/Наименование/Вид/subconto[]) →
   ПланыСчетов.X.СоздатьСчет, Вид=ВидСчета.<...>, subconto → ТЧ ВидыСубконто;
 - проводки: блок accounting_records[Регистр] (registrar + records со СчетДт/СчетКт/
   Сумма; СубконтоДт/СубконтоКт = {видСубконто_ref: значение_ref} → запись по индексу);
 - движения регистра накопления: документ-регистратор + НаборЗаписей с
   Отбор.Регистратор (без регистратора стандартный регистр не записать);
 - ВидДвижения: Приход (по умолчанию) | Расход — поле «ВидДвижения» в записи РН
   → ВидДвиженияНакопления.<значение> (расходные движения для оборотов/контроля);
 - записи независимого регистра сведений: МенеджерЗаписи (регистратор не нужен);
 - значение-дата в YAML (date) → Дата(ГГГГ,ММ,ДД) — для Период/Дата документа;
 - значение "$регистратор" в поле записи РН → ссылка на документ-регистратор
   этой записи (измерение «Партия» в FIFO-задачах).
"""

from __future__ import annotations

import datetime


def _bsl_str(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def _bsl_value(value, var_names: dict[str, str]) -> str:
    """Значение поля записи → выражение BSL (ссылка/перечисление/булево/число/дата/строка)."""
    if isinstance(value, str) and value in var_names:
        return var_names[value]
    if isinstance(value, str) and (
        value.startswith("Перечисления.") or value.startswith("Справочники.")
    ):
        return value  # готовое BSL: Перечисления.X.Y / Справочники.X.Предопределённый
    if isinstance(value, (datetime.date, datetime.datetime)):
        return f"Дата({value.year}, {value.month}, {value.day})"
    if isinstance(value, bool):
        return "Истина" if value else "Ложь"
    if isinstance(value, (int, float)):
        return str(value)
    return _bsl_str(value)


def generate_fixtures_module(fixtures: dict) -> str:
    """fixtures.yaml (dict) → BSL: Спр() + СоздатьФикстуры()."""
    lines: list[str] = []

    # — универсальный поиск ссылки (нужен и проверкам задачи)
    lines += [
        "Функция Спр(ИмяСправочника, Наименование) Экспорт",
        "\tВозврат Справочники[ИмяСправочника].НайтиПоНаименованию(Наименование, Истина);",
        "КонецФункции",
        "",
    ]

    body: list[str] = []
    var_names: dict[str, str] = {}  # ref → имя переменной BSL

    # — справочники: элементы и группы, иерархия по parent (порядок YAML = родители раньше).
    #   Служебные ключи — ниже в cat_reserved; прочие ключи трактуются как РЕКВИЗИТЫ
    #   справочника (config_spec.catalogs.<имя>.attributes) и присваиваются объекту.
    cat_reserved = {"ref", "Наименование", "isFolder", "parent", "owner"}
    for cat_name, items in (fixtures.get("catalogs") or {}).items():
        for item in items:
            ref = item["ref"]
            var = f"Ф_{ref}"
            var_names[ref] = var
            kind = "СоздатьГруппу" if item.get("isFolder") else "СоздатьЭлемент"
            body.append(f"\t{var}Об = Справочники.{cat_name}.{kind}();")
            body.append(f"\t{var}Об.Наименование = {_bsl_str(item['Наименование'])};")
            owner = item.get("owner")  # подчинённый справочник: владелец обязателен
            if owner:
                ovar = var_names.get(owner)
                if ovar is None:
                    raise ValueError(
                        f"fixtures: owner «{owner}» объявлен позже подчинённого «{ref}» — "
                        f"владельцы должны идти раньше в YAML"
                    )
                body.append(f"\t{var}Об.Владелец = {ovar};")
            parent = item.get("parent")
            if parent:
                pvar = var_names.get(parent)
                if pvar is None:
                    raise ValueError(
                        f"fixtures: parent «{parent}» объявлен позже ребёнка «{ref}» — "
                        f"родители должны идти раньше в YAML"
                    )
                body.append(f"\t{var}Об.Родитель = {pvar};")
            for field, value in item.items():
                if field in cat_reserved:
                    continue
                if isinstance(value, list):  # табличная часть справочника: строки-словари
                    for row in value:
                        body.append(f"\tСтр = {var}Об.{field}.Добавить();")
                        for col, cval in row.items():
                            body.append(f"\tСтр.{col} = {_bsl_value(cval, var_names)};")
                    continue
                body.append(f"\t{var}Об.{field} = {_bsl_value(value, var_names)};")
            body.append(f"\t{var}Об.Записать(); {var} = {var}Об.Ссылка;")
            body.append("")

    # — виды характеристик/субконто (элементы ПВХ): создаются ДАННЫМИ. ТипЗначения —
    #   описание типа значения характеристики. Объявляются РАНЬШЕ счетов (счёт ссылается
    #   на вид субконто) и проводок.
    for pvc_name, kinds in (fixtures.get("characteristics") or {}).items():
        for kind in kinds:
            ref = kind["ref"]
            var = f"ВС_{ref}"
            var_names[ref] = var
            body.append(f"\t{var}Об = ПланыВидовХарактеристик.{pvc_name}.СоздатьЭлемент();")
            body.append(f"\t{var}Об.Наименование = {_bsl_str(kind['Наименование'])};")
            if kind.get("ТипЗначения"):
                body.append(
                    f"\t{var}Об.ТипЗначения = Новый ОписаниеТипов({_bsl_str(kind['ТипЗначения'])});"
                )
            body.append(f"\t{var}Об.Записать(); {var} = {var}Об.Ссылка;")
            body.append("")

    # — счета плана счетов: создаются ДАННЫМИ (не метаданными). Вид — системное
    #   перечисление ВидСчета (Активный/Пассивный/АктивноПассивный). Ключ subconto —
    #   список ref видов субконто (ТЧ ВидыСубконто счёта). Ключ parent — ref счёта-родителя
    #   (субсчёт; для запросов В ИЕРАРХИИ); родитель объявляется РАНЬШЕ субсчёта. Счета
    #   объявляются РАНЬШЕ проводок (проводки ссылаются на них по ref).
    for chart_name, accounts in (fixtures.get("accounts") or {}).items():
        for acc in accounts:
            ref = acc["ref"]
            var = f"Сч_{ref}"
            var_names[ref] = var
            body.append(f"\t{var}Об = ПланыСчетов.{chart_name}.СоздатьСчет();")
            body.append(f"\t{var}Об.Код = {_bsl_str(acc['Код'])};")
            body.append(
                f"\t{var}Об.Наименование = {_bsl_str(acc.get('Наименование', acc['Код']))};"
            )
            if acc.get("Вид"):
                body.append(f"\t{var}Об.Вид = ВидСчета.{acc['Вид']};")
            parent = acc.get("parent")  # субсчёт: родитель раньше в YAML
            if parent:
                pvar = var_names.get(parent)
                if pvar is None:
                    raise ValueError(
                        f"fixtures: parent-счёт «{parent}» объявлен позже субсчёта «{ref}» — "
                        f"родительские счета должны идти раньше в YAML"
                    )
                body.append(f"\t{var}Об.Родитель = {pvar};")
            for subref in acc.get("subconto", []):
                body.append(f"\t{var}Об.ВидыСубконто.Добавить().ВидСубконто = {var_names[subref]};")
            body.append(f"\t{var}Об.Записать(); {var} = {var}Об.Ссылка;")
            body.append("")

    # — движения регистров накопления: документ-регистратор + набор записей.
    #   Поле «Период» (date в YAML) задаёт и дату документа — порядок партий FIFO;
    #   «$регистратор» в значении поля → ссылка на документ этой записи.
    for reg_name, block in (fixtures.get("register_records") or {}).items():
        registrar = block.get("registrar")
        if not registrar:
            raise ValueError(
                f"fixtures: у регистра «{reg_name}» не задан registrar — "
                f"движения без документа-регистратора не записываются"
            )
        for rec in block.get("records", []):
            period = _bsl_value(rec["Период"], var_names) if "Период" in rec else "ТекущаяДата()"
            body.append(f"\tДок = Документы.{registrar}.СоздатьДокумент();")
            body.append(f"\tДок.Дата = {period}; Док.Записать();")
            body.append(f"\tНабор = РегистрыНакопления.{reg_name}.СоздатьНаборЗаписей();")
            body.append("\tНабор.Отбор.Регистратор.Установить(Док.Ссылка);")
            body.append(f"\tЗ = Набор.Добавить(); З.Регистратор = Док.Ссылка; З.Период = {period};")
            for field, value in rec.items():
                if field == "Период":
                    continue
                if field == "ВидДвижения":
                    # Приход (по умолчанию у нового движения) | Расход — расходные движения
                    body.append(f"\tЗ.ВидДвижения = ВидДвиженияНакопления.{value};")
                elif value == "$регистратор":
                    body.append(f"\tЗ.{field} = Док.Ссылка;")
                else:
                    body.append(f"\tЗ.{field} = {_bsl_value(value, var_names)};")
            body.append("\tНабор.Записать();")
            body.append("")

    # — записи независимых регистров сведений: МенеджерЗаписи, регистратор не нужен
    for reg_name, records in (fixtures.get("info_records") or {}).items():
        for rec in records:
            body.append(f"\tМЗ = РегистрыСведений.{reg_name}.СоздатьМенеджерЗаписи();")
            for field, value in rec.items():
                body.append(f"\tМЗ.{field} = {_bsl_value(value, var_names)};")
            body.append("\tМЗ.Записать();")
            body.append("")

    # — записи ПОДЧИНЁННОГО регистра сведений (write_mode RecorderSubordinate): пишутся
    #   проведением документа → как у накопления, набор записей с Отбор.Регистратор,
    #   но без ВидДвижения. «Период» задаёт и дату документа-регистратора.
    for reg_name, block in (fixtures.get("info_register_records") or {}).items():
        registrar = block.get("registrar")
        if not registrar:
            raise ValueError(f"fixtures: у подчинённого РС «{reg_name}» не задан registrar")
        for rec in block.get("records", []):
            period = _bsl_value(rec["Период"], var_names) if "Период" in rec else "ТекущаяДата()"
            body.append(f"\tДок = Документы.{registrar}.СоздатьДокумент();")
            body.append(f"\tДок.Дата = {period}; Док.Записать();")
            body.append(f"\tНабор = РегистрыСведений.{reg_name}.СоздатьНаборЗаписей();")
            body.append("\tНабор.Отбор.Регистратор.Установить(Док.Ссылка);")
            body.append(f"\tЗ = Набор.Добавить(); З.Регистратор = Док.Ссылка; З.Период = {period};")
            for field, value in rec.items():
                if field == "Период":
                    continue
                body.append(f"\tЗ.{field} = {_bsl_value(value, var_names)};")
            body.append("\tНабор.Записать();")
            body.append("")

    # — проводки регистра бухгалтерии: документ-регистратор + набор записей с
    #   корреспонденцией СчетДт/СчетКт и ресурсом Сумма (поля задаются прямо в записи).
    #   Счета — по ref (объявлены в accounts выше). Период задаёт и дату документа.
    for reg_name, block in (fixtures.get("accounting_records") or {}).items():
        registrar = block.get("registrar")
        if not registrar:
            raise ValueError(f"fixtures: у регистра бухгалтерии «{reg_name}» не задан registrar")
        for rec in block.get("records", []):
            period = _bsl_value(rec["Период"], var_names) if "Период" in rec else "ТекущаяДата()"
            body.append(f"\tДок = Документы.{registrar}.СоздатьДокумент();")
            body.append(f"\tДок.Дата = {period}; Док.Записать();")
            body.append(f"\tНабор = РегистрыБухгалтерии.{reg_name}.СоздатьНаборЗаписей();")
            body.append("\tНабор.Отбор.Регистратор.Установить(Док.Ссылка);")
            body.append(f"\tЗ = Набор.Добавить(); З.Регистратор = Док.Ссылка; З.Период = {period};")
            for field, value in rec.items():
                if field == "Период":
                    continue
                # субконто проводки: {видСубконто_ref: значение_ref} → запись по индексу
                # (вид субконто): З.СубконтоДт[ВидСубконто] = Значение
                if field in ("СубконтоДт", "СубконтоКт") and isinstance(value, dict):
                    for kind_ref, val in value.items():
                        body.append(
                            f"\tЗ.{field}[{var_names[kind_ref]}] = {_bsl_value(val, var_names)};"
                        )
                    continue
                body.append(f"\tЗ.{field} = {_bsl_value(value, var_names)};")
            body.append("\tНабор.Записать();")
            body.append("")

    # — константы: единственное значение конфигурации (базовая валюта/организация)
    for name, value in (fixtures.get("constants") or {}).items():
        body.append(f"\tКонстанты.{name}.Установить({_bsl_value(value, var_names)});")
    if fixtures.get("constants"):
        body.append("")

    lines.append("Процедура СоздатьФикстуры() Экспорт")
    # объявление переменных не нужно — в BSL присваивание объявляет локальную
    lines += body if body else ["\t// фикстур нет"]
    lines.append("КонецПроцедуры")
    return "\n".join(lines) + "\n"
