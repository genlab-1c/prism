"""Параметрическая синтетика: дистракторы и рендер схемы для модели.

Зачем (см. docs/synthetic-config.md в prism-concept): крошечная per-task конфа честно
меряет механику, но убивает проблему ВЫБОРА объекта (вся схема влезает в промпт) — а на
ней держится и реальная сложность категории B, и смысл замера MCP-эффекта. Решение —
программно наращивать схему правдоподобными дистракторами с управляемыми параметрами:

    spec = add_distractors(spec, n_registers=20, n_catalogs=10, seed=42)

Свойства:
 - детерминированно по seed (воспроизводимость прогона);
 - целевые объекты задачи не трогаются, коллизии имён исключены;
 - дистракторы-регистры накопления получают общего регистратора (требование платформы);
 - похожесть имён можно усиливать (стресс-тест: модели труднее выбрать нужный объект).

render_schema(spec) — текст метаданных, который подаётся модели как контекст
(режим full-dump; в режиме MCP та же спека отдаётся через инструменты).

Пакет самодостаточен (только стандартная библиотека) — пригоден к выносу в отдельный
репозиторий. Никаких импортов из prism.
"""

from __future__ import annotations

import copy
import random

# Банки морфем для правдоподобных имён (домен торговли/склада — как в типовых)
_REG_FIRST = ["Товары", "Остатки", "Партии", "Резервы", "Заказы", "Материалы", "Грузы"]
_REG_SECOND = ["НаСкладах", "КОтгрузке", "ВРезерве", "ВПути", "Переданные", "Полученные",
               "КПоступлению", "Организаций", "НаКомиссии"]
_RES_NAMES = ["Количество", "ВНаличии", "КОтгрузке", "Заказано", "Свободно", "Сумма", "Вес"]
_CAT_NAMES = ["МестаХранения", "ТочкиДоставки", "Контрагенты", "Подразделения", "Организации",
              "ГруппыДоступа", "ВидыЗапасов", "СтатусыПартий", "Грузоперевозчики", "ЕдиницыИзмерения",
              "Договоры", "Соглашения", "Сегменты", "Менеджеры", "Маршруты"]
_INFOREG_FIRST = ["Цены", "Курсы", "Тарифы", "Скидки", "Лимиты", "Нормативы"]
_INFOREG_SECOND = ["Номенклатуры", "Поставщиков", "Контрагентов", "Доставки", "Хранения", "Закупок"]

DISTRACTOR_REGISTRAR = "РегистрацияДвижений"   # общий документ-регистратор для дистракторов


def add_distractors(spec: dict, n_registers: int = 10, n_catalogs: int = 8,
                    n_inforegs: int = 6, seed: int = 42) -> dict:
    """Вернуть копию спеки, дополненную дистракторами. Целевые объекты не изменяются."""
    rng = random.Random(seed)
    out = copy.deepcopy(spec)
    out.setdefault("catalogs", {})
    out.setdefault("accumulation_registers", {})
    out.setdefault("information_registers", {})
    out.setdefault("documents", {})

    taken = (set(out["catalogs"]) | set(out["accumulation_registers"])
             | set(out["information_registers"]) | set(out["documents"]))

    def fresh(gen) -> str:
        for _ in range(1000):
            name = gen()
            if name not in taken:
                taken.add(name)
                return name
        raise RuntimeError("исчерпаны комбинации имён — уменьшите n или расширьте банки морфем")

    # справочники-дистракторы (нужны и как типы измерений)
    cat_pool = []
    for _ in range(n_catalogs):
        name = fresh(lambda: rng.choice(_CAT_NAMES) + rng.choice(["", "Компании", "Основные"]))
        out["catalogs"][name] = {"hierarchical": rng.random() < 0.3}
        cat_pool.append(name)
    dim_sources = cat_pool + list(spec.get("catalogs", {}))

    # регистры накопления-дистракторы (+ общий регистратор)
    reg_names = []
    for _ in range(n_registers):
        name = fresh(lambda: rng.choice(_REG_FIRST) + rng.choice(_REG_SECOND))
        dims = {f"Измерение{i + 1}" if rng.random() < 0.2 else dim: {"type": f"СправочникСсылка.{dim}"}
                for i, dim in enumerate(rng.sample(dim_sources, k=min(2, len(dim_sources))))}
        ress = {res: {"type": "Число", "length": 15, "precision": rng.choice([0, 2, 3])}
                for res in rng.sample(_RES_NAMES, k=rng.randint(1, 2))}
        out["accumulation_registers"][name] = {
            "dimensions": dims, "resources": ress,
            "register_type": "Balance" if rng.random() < 0.8 else "Turnovers"}
        reg_names.append(name)
    if reg_names:
        out["documents"].setdefault(DISTRACTOR_REGISTRAR, {"registers": []})
        out["documents"][DISTRACTOR_REGISTRAR].setdefault("registers", []).extend(reg_names)

    # регистры сведений-дистракторы (независимые, регистратор не нужен)
    for _ in range(n_inforegs):
        name = fresh(lambda: rng.choice(_INFOREG_FIRST) + rng.choice(_INFOREG_SECOND))
        dim = rng.choice(dim_sources)
        out["information_registers"][name] = {
            "periodicity": rng.choice(["Day", "Month"]),
            "dimensions": {dim: {"type": f"СправочникСсылка.{dim}"}},
            "resources": {rng.choice(["Значение", "Цена", "Курс", "Процент"]):
                          {"type": "Число", "length": 15, "precision": 2}}}
    return out


def render_schema(spec: dict) -> str:
    """Текст метаданных конфигурации — контекст для модели (детерминированный порядок)."""
    lines = ["Метаданные конфигурации:"]

    if spec.get("constants"):
        lines.append("\nКонстанты:")
        for name in sorted(spec["constants"]):
            lines.append(f"- Константа.{name} ({_t(spec['constants'][name])})")

    if spec.get("enums"):
        lines.append("\nПеречисления:")
        for name in sorted(spec["enums"]):
            lines.append(f"- Перечисление.{name}: {', '.join(spec['enums'][name])}")

    if spec.get("catalogs"):
        lines.append("\nСправочники:")
        for name in sorted(spec["catalogs"]):
            cat = spec["catalogs"][name]
            hier = " (иерархический: группы и элементы)" if cat.get("hierarchical") else ""
            lines.append(f"- Справочник.{name}{hier}")
            for attr, t in cat.get("attributes", {}).items():
                lines.append(f"    Реквизит: {attr} ({_t(t)})")
            for ts, ts_spec in cat.get("tabular_sections", {}).items():
                cols = ", ".join(f"{a} ({_t(t)})" for a, t in ts_spec.get("attributes", {}).items())
                lines.append(f"    Табличная часть {ts}: {cols}")
            if cat.get("predefined"):
                names = ", ".join(i if isinstance(i, str) else i["name"] for i in cat["predefined"])
                lines.append(f"    Предопределённые: {names}")

    if spec.get("documents"):
        lines.append("\nДокументы:")
        for name in sorted(spec["documents"]):
            doc = spec["documents"][name]
            lines.append(f"- Документ.{name}")
            for attr, t in doc.get("attributes", {}).items():
                lines.append(f"    Реквизит: {attr} ({_t(t)})")
            for ts, ts_spec in doc.get("tabular_sections", {}).items():
                cols = ", ".join(f"{a} ({_t(t)})" for a, t in ts_spec.get("attributes", {}).items())
                lines.append(f"    Табличная часть {ts}: {cols}")
            if doc.get("registers"):
                lines.append(f"    Движения: {', '.join(doc['registers'])}")

    if spec.get("accumulation_registers"):
        lines.append("\nРегистрыНакопления:")
        for name in sorted(spec["accumulation_registers"]):
            reg = spec["accumulation_registers"][name]
            kind = "остатки" if reg.get("register_type", "Balance") == "Balance" else "обороты"
            dims = ", ".join(f"{d} ({_t(t)})" for d, t in reg.get("dimensions", {}).items())
            ress = ", ".join(f"{r} ({_t(t)})" for r, t in reg.get("resources", {}).items())
            lines.append(f"- РегистрНакопления.{name} (вид: {kind})")
            lines.append(f"    Измерения: {dims}")
            lines.append(f"    Ресурсы: {ress}")

    if spec.get("information_registers"):
        lines.append("\nРегистрыСведений:")
        for name in sorted(spec["information_registers"]):
            reg = spec["information_registers"][name]
            dims = ", ".join(f"{d} ({_t(t)})" for d, t in reg.get("dimensions", {}).items())
            ress = ", ".join(f"{r} ({_t(t)})" for r, t in reg.get("resources", {}).items())
            mode = ("подчинён регистратору — пишется проведением документа"
                    if reg.get("write_mode") == "RecorderSubordinate" else "независимый")
            lines.append(f"- РегистрСведений.{name} (периодический: {reg.get('periodicity', 'Day')}, {mode})")
            lines.append(f"    Измерения: {dims}")
            lines.append(f"    Ресурсы: {ress}")

    return "\n".join(lines) + "\n"


def _t(type_spec: dict) -> str:
    t = type_spec.get("type", "Число")
    if isinstance(t, list):                      # составной тип → нужен ВЫРАЗИТЬ(... КАК ...)
        return "составной (" + ", ".join(t) + ")"
    if t == "Число":
        return f"Число {type_spec.get('length', 15)}.{type_spec.get('precision', 0)}"
    if t == "Строка":
        return f"Строка {type_spec.get('length', 100)}"
    return t                                      # Дата / Булево / СправочникСсылка.X / ПеречислениеСсылка.X
