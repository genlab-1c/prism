"""Контекст метаданных для агентного режима генерации.

MetadataProvider — контракт инструментов навигации по метаданным («список / поиск /
структура объекта»), которыми агент-loader находит нужные объекты среди многих.
SpecMetadataProvider — реализация поверх синтетического спека задачи (config_spec),
в процессе, без живой 1С. Раздувание спека дистракторами — забота вызывающего.
"""

from .base import MetadataProvider
from .spec_provider import SpecMetadataProvider

__all__ = ["MetadataProvider", "SpecMetadataProvider"]
