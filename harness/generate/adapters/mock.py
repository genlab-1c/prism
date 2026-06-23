"""Офлайновый адаптер для сухого прогона конвейера (prism generate --mock).

Сеть не трогает: на промпт задачи отдаёт заранее известный ответ — эталон задачи
(mode=canonical) или тривиальную заглушку (mode=stub). Нужен, чтобы новичок прогнал
весь путь генерация→оценка→лидерборд, не тратя ни ключей, ни денег.
"""

from __future__ import annotations

from ..types import ChatMessage, LLMResult
from .base import Adapter


class MockAdapter(Adapter):
    """Возвращает фиксированный ответ по тексту user-промпта (без сети).

    responses — карта {промпт задачи: готовый ответ с ```-блоком}; на неизвестный
    промпт отдаём stub. Токены проставляем грубо (≈ символы/4) — стоимость прогона
    всё равно ноль (mock-модель в pricing с нулевой ценой).
    """

    name = "mock"
    supports_seed = False
    supports_tools = False

    def __init__(self, responses: dict[str, str], *, stub: str):
        super().__init__()
        self._responses = responses
        self._stub = stub

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
        prompt = next((m.content for m in reversed(messages) if m.role == "user"), "")
        content = self._responses.get(prompt, self._stub)
        tokens_in = max(1, len(prompt) // 4)
        tokens_out = max(1, len(content) // 4)
        return LLMResult(
            success=True,
            content=content,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            tokens_total=tokens_in + tokens_out,
            elapsed=0.0,
            model_used=model_id,
        )
