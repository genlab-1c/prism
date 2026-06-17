"""synthconfig — генератор синтетической конфигурации 1С из декларативной YAML-спеки.

Самодостаточный пакет (только стандартная библиотека, без зависимостей от prism):
описываешь справочники/документы/регистры на YAML — получаешь дерево XML формата
`/LoadConfigFromFiles`, готовое к загрузке в 1С. Плюс детерминированная догенерация
«шумовых» объектов (дистракторов) для масштабирования схемы.

Спроектирован к выносу в отдельный публичный репозиторий: внутри prism живёт как
обычный модуль, после стабилизации отщипывается без правок и подключается обратно
по закреплённой версии. См. README.md.

Публичный интерфейс:
    build(spec, empty_cfg, out_cfg)          — собрать дерево конфигурации из спеки
    catalog_xml / accumreg_xml /
    information_register_xml / document_xml /
    enum_xml / constant_xml                   — XML отдельных объектов
    add_distractors(spec, ...)               — нарастить схему дистракторами (по seed)
    render_schema(spec)                      — текст схемы для контекста модели
"""

from __future__ import annotations

from .build_config import (
    accumreg_xml,
    build,
    catalog_xml,
    constant_xml,
    document_xml,
    enum_xml,
    information_register_xml,
)
from .synth import add_distractors, render_schema

__all__ = [
    "build",
    "catalog_xml",
    "accumreg_xml",
    "information_register_xml",
    "document_xml",
    "enum_xml",
    "constant_xml",
    "add_distractors",
    "render_schema",
]
