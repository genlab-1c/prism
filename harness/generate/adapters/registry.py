"""Сборка адаптера по имени из models.yaml (access.adapter) + креды из окружения.

Креды — только из env (не в репозитории):
  openrouter    OPENROUTER_API_KEY
  openai_compat OPENAI_COMPAT_API_KEY (необязательно для локали) + endpoint из access
  gigachat      GIGACHAT_AUTH_KEY [+ GIGACHAT_SCOPE]
  yandexgpt     YANDEX_API_KEY + YANDEX_FOLDER_ID
"""

from __future__ import annotations

import os

from ..transport import Transport
from .base import Adapter
from .gigachat import GigaChatAdapter
from .openai_compat import OpenAICompatAdapter
from .yandexgpt import YandexGPTAdapter

ADAPTERS = ("openrouter", "openai_compat", "gigachat", "yandexgpt")

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class AdapterConfigError(RuntimeError):
    """Не хватает кред/настроек для адаптера (понятная ошибка вместо падения в сети)."""


def _require(env: dict, key: str, adapter: str) -> str:
    val = env.get(key)
    if not val:
        raise AdapterConfigError(f"адаптер {adapter}: в окружении нет {key}")
    return val


def build_adapter(adapter_name: str, *, endpoint: str | None = None,
                  env: dict | None = None, transport: Transport | None = None,
                  timeout: int = 120) -> Adapter:
    """Сконструировать адаптер по имени. endpoint — из access.endpoint (для openai_compat)."""
    env = os.environ if env is None else env

    if adapter_name == "openrouter":
        return OpenAICompatAdapter(
            base_url=_OPENROUTER_BASE,
            api_key=_require(env, "OPENROUTER_API_KEY", adapter_name),
            transport=transport, timeout=timeout,
            extra_headers={"HTTP-Referer": "https://github.com/genlab-1c/prism",
                           "X-Title": "PRISM"})

    if adapter_name == "openai_compat":
        if not endpoint:
            raise AdapterConfigError("адаптер openai_compat: не задан access.endpoint")
        return OpenAICompatAdapter(
            base_url=endpoint, api_key=env.get("OPENAI_COMPAT_API_KEY"),
            transport=transport, timeout=timeout)

    if adapter_name == "gigachat":
        return GigaChatAdapter(
            auth_key=_require(env, "GIGACHAT_AUTH_KEY", adapter_name),
            scope=env.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            transport=transport, timeout=timeout)

    if adapter_name == "yandexgpt":
        return YandexGPTAdapter(
            api_key=_require(env, "YANDEX_API_KEY", adapter_name),
            folder_id=_require(env, "YANDEX_FOLDER_ID", adapter_name),
            transport=transport, timeout=timeout)

    raise AdapterConfigError(f"неизвестный адаптер {adapter_name!r}; есть: {ADAPTERS}")
