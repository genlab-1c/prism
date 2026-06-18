"""Базовый контракт адаптера LLM.

Адаптер ничего не знает о бенчмарке (детерминизм, хеши, прогоны — слоем выше);
его дело — вызвать API провайдера и привести ответ к LLMResult. Возможности
(seed/tools) объявляются классом честно: оркестратор по ним решает, что слать.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from ..transport import HttpResponse, Transport, default_transport
from ..types import ChatMessage, LLMResult


def http_error(resp: HttpResponse) -> str:
    """Человекочитаемая ошибка из не-200 ответа (разные провайдеры — разные поля)."""
    msg = f"HTTP {resp.status_code}"
    body = resp.body
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return f"{msg}: {err.get('message', err)}"
        if err:
            return f"{msg}: {err}"
        if body.get("message"):
            return f"{msg}: {body['message']}"
    return f"{msg}: {(resp.text or '')[:200]}"


class Adapter(ABC):
    """Единый контракт: chat(model_id, messages, ...) -> LLMResult."""

    name: str = "adapter"
    supports_seed: bool = False
    supports_tools: bool = False

    def __init__(self, transport: Transport | None = None, timeout: int = 120):
        self.transport = transport or default_transport
        self.timeout = timeout

    @abstractmethod
    def chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        seed: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResult:
        """Один вызов генерации. Неподдерживаемые параметры адаптер молча игнорирует."""
        ...

    # ── общая обвязка: таймер + ловля сетевых ошибок ─────────────────────────
    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        data: dict | None = None,
    ) -> tuple[HttpResponse | None, float, str | None]:
        """(ответ|None, прошло_сек, ошибка|None). Исключение транспорта → ошибка, не падение."""
        start = time.time()
        try:
            resp = self.transport.request(
                method, url, headers=headers, json=json, data=data, timeout=self.timeout
            )
            return resp, time.time() - start, None
        except Exception as e:  # noqa: BLE001 — сеть: возвращаем как failure
            return None, time.time() - start, str(e)
