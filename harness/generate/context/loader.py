"""Агентный загрузчик контекста — режим «найти нужное среди многих».

Модели дают задачу + инструменты MetadataProvider (+ finish_research); она сама
навигирует по метаданным (list/search/structure), а когда собрала достаточно — зовёт
finish_research. Собранные структуры объектов идут в контекст генерации кода.

Развязан от провайдера и от модели: на вход — любой Adapter (LLM) и любой
MetadataProvider. Синхронный (adapter.chat синхронный). Метрики сохранены: итерации,
вызовы инструментов, токены, выбранные объекты — материал для оси «навигация».
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from ..adapters.base import Adapter
from ..types import ChatMessage
from .base import MetadataProvider

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_research",
        "description": "Завершить исследование метаданных, когда собрано достаточно для кода.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "какие объекты используешь и почему"}
            },
            "required": ["summary"],
        },
    },
}

_SYSTEM = (
    "Ты эксперт по 1С:Предприятие. По описанию задачи найди в конфигурации нужные "
    "объекты метаданных через инструменты: list_objects/search_objects — чтобы найти "
    "кандидатов, get_object_structure — чтобы изучить структуру выбранного объекта. "
    "Когда собрал достаточно для написания кода — вызови finish_research с кратким резюме. "
    "Не выдумывай объекты, которых нет в конфигурации."
)
_USER = "Задача:\n{task}\n\nНайди нужные объекты метаданных."

# инструменты-исследования, чьи результаты складываются в контекст (не служебные)
_STRUCTURE_TOOL = "get_object_structure"


class ContextResult(BaseModel):
    """Итог сбора контекста агентом."""

    success: bool
    context_text: str = ""
    objects_loaded: list[str] = Field(default_factory=list)
    summary: str = ""  # резюме из finish_research
    iterations: int = 0
    tool_calls: int = 0
    tokens: int = 0
    tokens_input: int = 0  # для учёта стоимости агентного сбора (кат. B)
    tokens_output: int = 0
    error: str | None = None


class AgenticContextLoader:
    def __init__(
        self,
        adapter: Adapter,
        provider: MetadataProvider,
        model_id: str,
        *,
        system_prompt: str = _SYSTEM,
        user_template: str = _USER,
        max_iterations: int = 8,
        max_objects: int = 5,
        max_context_chars: int = 15000,
    ):
        self.adapter = adapter
        self.provider = provider
        self.model_id = model_id
        self.system_prompt = system_prompt
        self.user_template = user_template
        self.max_iterations = max_iterations
        self.max_objects = max_objects
        self.max_context_chars = max_context_chars

    def load(self, task_prompt: str) -> ContextResult:
        tools = self.provider.tools() + [FINISH_TOOL]
        messages = [
            ChatMessage.system(self.system_prompt),
            ChatMessage.user(self.user_template.format(task=task_prompt)),
        ]
        res = ContextResult(success=True)
        collected: list[str] = []

        for it in range(self.max_iterations):
            res.iterations = it + 1
            out = self.adapter.chat(self.model_id, messages, temperature=0.0, tools=tools)
            res.tokens += out.tokens_total
            res.tokens_input += out.tokens_input
            res.tokens_output += out.tokens_output
            if not out.success:
                return ContextResult(
                    success=False,
                    error=out.error,
                    iterations=res.iterations,
                    tokens=res.tokens,
                    tokens_input=res.tokens_input,
                    tokens_output=res.tokens_output,
                )
            if not out.tool_calls:
                break  # модель не зовёт инструменты — закончили

            messages.append(ChatMessage.assistant(out.content or "", tool_calls=out.tool_calls))
            for tc in out.tool_calls:
                res.tool_calls += 1
                args = _parse_args(tc.arguments_raw)
                if tc.name == "finish_research":
                    res.summary = args.get("summary", "")
                    res.context_text = "\n\n---\n\n".join(collected)
                    res.objects_loaded = list(res.objects_loaded)
                    return res
                result_text = self.provider.call(tc.name, args)
                messages.append(
                    ChatMessage.tool_response(result_text, tool_call_id=tc.id, name=tc.name)
                )

                # в контекст идут только успешные структуры объектов
                if tc.name == _STRUCTURE_TOOL and "не найден" not in result_text:
                    collected.append(result_text)
                    res.objects_loaded.append(args.get("name", ""))
                    if len(res.objects_loaded) >= self.max_objects:
                        res.context_text = "\n\n---\n\n".join(collected)
                        return res
                    if sum(len(c) for c in collected) >= self.max_context_chars:
                        res.context_text = "\n\n---\n\n".join(collected)
                        return res

        res.context_text = "\n\n---\n\n".join(collected)
        return res


def _parse_args(raw: str) -> dict:
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
