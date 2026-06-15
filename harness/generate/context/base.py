"""Контракт провайдера метаданных — инструменты навигации для агентного режима.

Агент-loader получает tools() (в OpenAI function-формате), модель вызывает их, loader
исполняет call() и собирает контекст. Реализаций может быть несколько (синтетический
спек сейчас, реальный MCP позже) — loader зависит только от этого контракта.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MetadataProvider(ABC):
    """Источник метаданных как набор вызываемых инструментов."""

    @abstractmethod
    def tools(self) -> list[dict]:
        """Определения инструментов в OpenAI function-формате (передаются модели)."""
        ...

    @abstractmethod
    def call(self, name: str, arguments: dict) -> str:
        """Исполнить вызов инструмента → текстовый результат для модели."""
        ...
