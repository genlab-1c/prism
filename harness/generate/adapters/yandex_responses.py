"""Адаптер Yandex Cloud Responses API — открытые модели (OpenAI gpt-oss и т.п.).

Отдельный канал от yandexgpt: gpt-oss обслуживается НЕ нативным
foundationModels/v1/completion, а OpenAI-совместимым Responses API на другом хосте:
  POST https://ai.api.cloud.yandex.net/v1/responses
  заголовки: Authorization: Api-Key <key> (или Bearer для IAM), OpenAI-Project: <folder>
  тело:  {modelUri в поле model: gpt://<folder>/<id>, instructions(=system),
          input(=диалог: строка либо массив элементов), tools?, max_output_tokens, temperature}
  ответ: {output: [ {type:"reasoning", summary:[...]},               # рассуждение
                    {type:"message", content:[{type:"output_text", text}]},  # ответ
                    {type:"function_call", call_id, name, arguments} ],       # вызов tool
          usage: {input_tokens, output_tokens, total_tokens}}

Reasoning у модели не отключается и расходует часть max_output_tokens — закладывайте запас
(оттого и увеличенный таймаут по умолчанию: холодный старт + рассуждение). Seed не
поддерживается. Function calling — в формате Responses: плоские tools (type+name+...),
в ответе элементы function_call, продолжение диалога — function_call_output во input.
"""

from __future__ import annotations

import json

from ..types import ChatMessage, LLMResult, ToolCall
from .base import Adapter, http_error

_BASE_URL = "https://ai.api.cloud.yandex.net"


def _split_messages(messages: list[ChatMessage]) -> tuple[str, list[dict] | None, str | None]:
    """ChatMessage[] → (instructions, input_items, simple_text).

    Системные сообщения → instructions. Если остаётся ровно одно user-сообщение без
    инструментов (кат. A и первый ход кат. B) — отдаём его строкой (проверенная схема).
    Иначе собираем массив input в формате Responses: role-сообщения + function_call
    (вызовы модели) / function_call_output (результаты инструментов).
    """
    instructions = "\n\n".join(m.content for m in messages if m.role == "system" and m.content)
    rest = [m for m in messages if m.role != "system"]
    if len(rest) == 1 and rest[0].role == "user" and not rest[0].tool_calls:
        return instructions, None, rest[0].content

    items: list[dict] = []
    for m in rest:
        if m.role == "tool":  # результат инструмента
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": m.tool_call_id or "",
                    "output": m.content,
                }
            )
        elif m.tool_calls:  # ход ассистента с вызовами инструментов
            if m.content:
                items.append({"role": "assistant", "content": m.content})
            for tc in m.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments_raw,
                    }
                )
        else:  # обычное текстовое сообщение
            items.append({"role": m.role, "content": m.content})
    return instructions, items, None


class YandexResponsesAdapter(Adapter):
    name = "yandex_responses"
    supports_seed = False
    supports_tools = True  # function calling в формате Responses API

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        base_url: str = _BASE_URL,
        iam: bool = False,
        reasoning_effort: str | None = None,
        transport=None,
        timeout: int = 300,  # reasoning может быть долгим + холодный старт → запас по времени
    ):
        super().__init__(transport, timeout)
        self.api_key = api_key
        self.folder_id = folder_id
        self.base_url = base_url.rstrip("/")
        self.iam = iam  # True → Bearer (IAM-токен), иначе Api-Key
        # "none" гасит reasoning (Qwen3.6 и др.) — иначе tools-запросы у Yandex зависают
        self.reasoning_effort = reasoning_effort

    def _model_uri(self, model_id: str) -> str:
        # уже полный URI — отдаём как есть, иначе собираем из folder_id
        return model_id if model_id.startswith("gpt://") else f"gpt://{self.folder_id}/{model_id}"

    def chat(
        self,
        model_id,
        messages,
        *,
        temperature=0.0,
        max_tokens=4096,
        seed=None,
        tools=None,
        tool_choice="auto",
    ) -> LLMResult:
        auth = f"Bearer {self.api_key}" if self.iam else f"Api-Key {self.api_key}"
        headers = {
            "Authorization": auth,
            "Content-Type": "application/json",
            "OpenAI-Project": self.folder_id,  # Responses API ждёт folder здесь
        }
        instructions, input_items, simple_text = _split_messages(messages)
        body: dict = {
            "model": self._model_uri(model_id),
            "instructions": instructions,
            "input": simple_text if simple_text is not None else input_items,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if self.reasoning_effort:  # "none" → reasoning выключен (быстрее, tools не виснут)
            body["reasoning_effort"] = self.reasoning_effort
        if tools:  # OpenAI chat-формат {function:{...}} → плоский Responses-формат
            body["tools"] = [{"type": "function", **t["function"]} for t in tools]
            body["tool_choice"] = tool_choice
        resp, elapsed, err = self._send(
            "POST", f"{self.base_url}/v1/responses", headers=headers, json=body
        )
        if err:
            return LLMResult.failure(f"{self.name}: {err}", elapsed)
        if resp.status_code != 200:
            return LLMResult.failure(http_error(resp), elapsed)
        return self._parse(resp.body, model_id, elapsed)

    @staticmethod
    def _parse(body: dict | None, model_id: str, elapsed: float) -> LLMResult:
        body = body or {}
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for o in body.get("output", []) or []:
            otype = o.get("type")
            if otype == "message":  # текст ответа (reasoning-элементы пропускаем)
                for c in o.get("content", []) or []:
                    if c.get("type") in ("output_text", "text") and c.get("text"):
                        text_parts.append(c["text"])
            elif otype == "function_call":
                args = o.get("arguments")
                if isinstance(args, dict | list):  # Responses может вернуть объект — в строку
                    args = json.dumps(args, ensure_ascii=False)
                tool_calls.append(
                    ToolCall(
                        id=o.get("call_id") or o.get("id", ""),
                        function={"name": o.get("name", ""), "arguments": args or "{}"},
                    )
                )
        usage = body.get("usage", {}) or {}
        ti = int(usage.get("input_tokens", usage.get("inputTextTokens", 0)) or 0)
        to = int(usage.get("output_tokens", usage.get("completionTokens", 0)) or 0)
        tt = int(usage.get("total_tokens", usage.get("totalTokens", 0)) or 0) or (ti + to)
        return LLMResult(
            success=True,
            content="\n".join(text_parts),
            tool_calls=tool_calls or None,
            tokens_input=ti,
            tokens_output=to,
            tokens_total=tt,
            elapsed=elapsed,
            model_used=body.get("model", model_id),
            raw=body,
        )
