"""Провайдер метаданных поверх синтетического спека задачи (config_spec).

В процессе, без живой 1С: читает тот же YAML, что и генератор базы (synthconfig),
и отвечает на инструменты навигации. Раздувание спека дистракторами (стог сена) —
ответственность вызывающего: сюда передаётся уже итоговый спек.

Инструменты (как у разработчика, исследующего конфигурацию):
  list_objects(kind?)          — перечень «Тип.Имя» (опц. фильтр по типу)
  search_objects(query)        — поиск объектов по подстроке имени
  get_object_structure(name)   — полная структура одного объекта
"""

from __future__ import annotations

from .base import MetadataProvider

# секция спека → русский тип объекта (как его называет 1С и ожидает модель)
_KINDS = {
    "catalogs": "Справочник",
    "documents": "Документ",
    "accumulation_registers": "РегистрНакопления",
    "information_registers": "РегистрСведений",
}


def _fmt_type(spec: dict) -> str:
    t = spec.get("type", "Число")
    if t == "Число":
        return f"Число {spec.get('length', 15)}.{spec.get('precision', 0)}"
    if t == "Строка":
        return f"Строка {spec.get('length', 100)}"
    return t  # СправочникСсылка.X / ДокументСсылка.X / Дата


def _fields(title: str, items: dict) -> list[str]:
    if not items:
        return []
    return [f"  {title}: " + ", ".join(f"{n} ({_fmt_type(s)})" for n, s in items.items())]


class SpecMetadataProvider(MetadataProvider):
    def __init__(self, spec: dict):
        self.spec = spec or {}
        # индекс: имя объекта → (секция, тип); и (тип, имя) для разрешения «Тип.Имя»
        self._index: dict[str, tuple[str, str]] = {}
        for section, type_name in _KINDS.items():
            for name in self.spec.get(section) or {}:
                self._index[name] = (section, type_name)

    # ── инструменты ──────────────────────────────────────────────────────────
    def tools(self) -> list[dict]:
        kinds = list(_KINDS.values())
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_objects",
                    "description": "Список объектов метаданных конфигурации в виде «Тип.Имя».",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": kinds,
                                "description": "тип объекта (необязательно)",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_objects",
                    "description": "Найти объекты метаданных по подстроке имени.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "часть имени объекта"}
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_object_structure",
                    "description": "Полная структура объекта: измерения/ресурсы/реквизиты/табличные части.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "имя объекта или «Тип.Имя»"}
                        },
                        "required": ["name"],
                    },
                },
            },
        ]

    def call(self, name: str, arguments: dict) -> str:
        args = arguments or {}
        if name == "list_objects":
            return self._list(args.get("kind"))
        if name == "search_objects":
            return self._search(args.get("query", ""))
        if name == "get_object_structure":
            return self._structure(args.get("name", ""))
        return f"неизвестный инструмент: {name}"

    # ── реализация инструментов ────────────────────────────────────────────────
    def _list(self, kind: str | None) -> str:
        lines = []
        for section, type_name in _KINDS.items():
            if kind and kind != type_name:
                continue
            for obj_name in self.spec.get(section) or {}:
                lines.append(f"{type_name}.{obj_name}")
        return "\n".join(lines) if lines else "(объектов нет)"

    def _search(self, query: str) -> str:
        q = (query or "").strip().lower()
        if not q:
            return "(пустой запрос)"
        hits = [f"{tn}.{n}" for n, (_s, tn) in self._index.items() if q in n.lower()]
        return "\n".join(sorted(hits)) if hits else f"(ничего не найдено по «{query}»)"

    def _resolve(self, name: str) -> tuple[str, str] | None:
        """«Тип.Имя» или «Имя» → (секция, имя_объекта) либо None."""
        bare = (
            name.split(".", 1)[1]
            if "." in name and name.split(".", 1)[0] in _KINDS.values()
            else name
        )
        hit = self._index.get(bare)
        return (hit[0], bare) if hit else None

    def _structure(self, name: str) -> str:
        resolved = self._resolve(name)
        if resolved is None:
            return f"объект «{name}» не найден в конфигурации"
        section, obj = resolved
        type_name = _KINDS[section]
        s = self.spec[section][obj]
        out = [f"{type_name}.{obj}"]

        if section == "catalogs":
            hier = (
                "иерархический (группы и элементы)" if s.get("hierarchical") else "не иерархический"
            )
            out.append(f"  {hier}")
            out += _fields("реквизиты", s.get("attributes") or {})
        elif section == "documents":
            out += _fields("реквизиты", s.get("attributes") or {})
            for ts, ts_spec in (s.get("tabular_sections") or {}).items():
                cols = ", ".join(
                    f"{n} ({_fmt_type(t)})" for n, t in (ts_spec.get("attributes") or {}).items()
                )
                out.append(f"  табличная часть {ts}: {cols}")
            if s.get("registers"):
                out.append(f"  движения по регистрам: {', '.join(s['registers'])}")
        elif section == "accumulation_registers":
            kind = "остатки" if s.get("register_type", "Balance") == "Balance" else "обороты"
            out.append(f"  вид: {kind}")
            out += _fields("измерения", s.get("dimensions") or {})
            out += _fields("ресурсы", s.get("resources") or {})
        elif section == "information_registers":
            out.append(f"  периодический: {s.get('periodicity', 'Day')}, независимый")
            out += _fields("измерения", s.get("dimensions") or {})
            out += _fields("ресурсы", s.get("resources") or {})

        return "\n".join(out)
