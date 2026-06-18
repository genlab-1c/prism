"""Единый контракт слоя генерации: сообщения, вызовы инструментов, результат.

Нормализованные типы, не зависящие от провайдера: каждый адаптер приводит свой
формат к ним. ChatMessage сериализуется в OpenAI-формат (его понимают OpenRouter,
Ollama, vLLM, GigaChat); YandexGPT переводит из ChatMessage в свой формат сам.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Вызов инструмента, запрошенный моделью (для агентного режима)."""

    id: str = ""
    type: Literal["function"] = "function"
    function: dict[str, Any] = Field(default_factory=dict)  # {name: str, arguments: str(JSON)}

    @property
    def name(self) -> str:
        return self.function.get("name", "")

    @property
    def arguments_raw(self) -> str:
        return self.function.get("arguments", "{}")


class ChatMessage(BaseModel):
    """Сообщение чата. Роли: system / user / assistant / tool."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] | None = None  # assistant с вызовами инструментов
    tool_call_id: str | None = None  # ответ tool
    name: str | None = None  # имя инструмента (tool response)

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> ChatMessage:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: list[ToolCall] | None = None) -> ChatMessage:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool_response(cls, content: str, tool_call_id: str, name: str | None = None) -> ChatMessage:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)

    def to_openai(self) -> dict[str, Any]:
        """Формат сообщения для OpenAI-совместимого API."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "type": tc.type, "function": tc.function} for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


class LLMResult(BaseModel):
    """Нормализованный результат одного вызова модели (через любой адаптер)."""

    success: bool
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    elapsed: float = 0.0
    model_used: str = ""
    error: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def failure(cls, error: str, elapsed: float = 0.0) -> LLMResult:
        return cls(success=False, error=error, elapsed=elapsed)
