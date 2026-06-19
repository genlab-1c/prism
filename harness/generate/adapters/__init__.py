"""Адаптеры LLM: единый контракт chat() поверх разных провайдеров.

  openai_compat — OpenRouter (облако) и локальные серверы (Ollama/vLLM/LM Studio)
  gigachat      — Sber GigaChat (OAuth-токен + чат)
  yandexgpt     — Yandex Cloud Foundation Models (свой формат completion)
  yandex_responses — Yandex Cloud Responses API (открытые модели: gpt-oss, Qwen3.6)

Выбор адаптера и кредов — registry.build_adapter() по access.adapter из models.yaml.
"""

from .base import Adapter
from .gigachat import GigaChatAdapter
from .openai_compat import OpenAICompatAdapter
from .registry import ADAPTERS, AdapterConfigError, build_adapter
from .yandex_responses import YandexResponsesAdapter
from .yandexgpt import YandexGPTAdapter

__all__ = [
    "Adapter",
    "OpenAICompatAdapter",
    "GigaChatAdapter",
    "YandexGPTAdapter",
    "YandexResponsesAdapter",
    "build_adapter",
    "ADAPTERS",
    "AdapterConfigError",
]
