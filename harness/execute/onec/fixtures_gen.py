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
    if isinstance(value, str) and value.startswith("Перечисления."):
        return value                       # уже валидное BSL: Перечисления.Имя.Значение
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
    var_names: dict[str, str] = {}   # ref → имя переменной BSL

    # — справочники: элементы и группы, иерархия по parent (порядок YAML = родители раньше).
    #   Служебные ключи — ниже в cat_reserved; прочие ключи трактуются как РЕКВИЗИТЫ
    #   справочника (config_spec.catalogs.<имя>.attributes) и присваиваются объекту.
    cat_reserved = {"ref", "Наименование", "isFolder", "parent"}
    for cat_name, items in (fixtures.get("catalogs") or {}).items():
        for item in items:
            ref = item["ref"]
            var = f"Ф_{ref}"
            var_names[ref] = var
            kind = "СоздатьГруппу" if item.get("isFolder") else "СоздатьЭлемент"
            body.append(f"\t{var}Об = Справочники.{cat_name}.{kind}();")
            body.append(f"\t{var}Об.Наименование = {_bsl_str(item['Наименование'])};")
            parent = item.get("parent")
            if parent:
                pvar = var_names.get(parent)
                if pvar is None:
                    raise ValueError(f"fixtures: parent «{parent}» объявлен позже ребёнка «{ref}» — "
                                     f"родители должны идти раньше в YAML")
                body.append(f"\t{var}Об.Родитель = {pvar};")
            for field, value in item.items():
                if field in cat_reserved:
                    continue
                if isinstance(value, list):       # табличная часть справочника: строки-словари
                    for row in value:
                        body.append(f"\tСтр = {var}Об.{field}.Добавить();")
                        for col, cval in row.items():
                            body.append(f"\tСтр.{col} = {_bsl_value(cval, var_names)};")
                    continue
                body.append(f"\t{var}Об.{field} = {_bsl_value(value, var_names)};")
            body.append(f"\t{var}Об.Записать(); {var} = {var}Об.Ссылка;")
            body.append("")

    # — движения регистров накопления: документ-регистратор + набор записей.
    #   Поле «Период» (date в YAML) задаёт и дату документа — порядок партий FIFO;
    #   «$регистратор» в значении поля → ссылка на документ этой записи.
    for reg_name, block in (fixtures.get("register_records") or {}).items():
        registrar = block.get("registrar")
        if not registrar:
            raise ValueError(f"fixtures: у регистра «{reg_name}» не задан registrar — "
                             f"движения без документа-регистратора не записываются")
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
