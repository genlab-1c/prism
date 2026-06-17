"""Адаптер Yandex Cloud Foundation Models (YandexGPT, Alice и др. serverless-модели).

Формат запроса/ответа НЕ совпадает с OpenAI, поэтому переводим вручную:
 - запрос: {modelUri, completionOptions, messages:[{role, text}], tools?};
 - ответ:  {result:{alternatives:[{message:{role, text | toolCallList}}], usage}}.
modelUri собирается из folder_id и id модели: gpt://<folder>/<model_id> (например
yandexgpt/latest). Seed не поддерживается. Function calling — в нативном формате Yandex
(toolCallList / toolResultList; arguments — ОБЪЕКТ, не строка). Авторизация — Api-Key
(или IAM-токен).
"""

from __future__ import annotations

import json

from ..types import ChatMessage, LLMResult, ToolCall
from .base import Adapter, http_error

_BASE_URL = "https://llm.api.cloud.yandex.net"


def _loads(raw: str) -> dict:
    """JSON-строка аргументов → объект (Yandex ждёт объект, ToolCall хранит строку)."""
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _to_yandex_message(m: ChatMessage) -> dict:
    """ChatMessage → сообщение Yandex: текст {role, text} либо нативные
    toolCallList (вызовы модели) / toolResultList (результаты инструментов)."""
    if m.tool_calls:
        return {"role": "assistant", "toolCallList": {"toolCalls": [
            {"functionCall": {"name": tc.name, "arguments": _loads(tc.arguments_raw)}}
            for tc in m.tool_calls]}}
    if m.role == "tool":
        return {"role": "assistant", "toolResultList": {"toolResults": [
            {"functionResult": {"name": m.name or "", "content": m.content}}]}}
    return {"role": m.role, "text": m.content}


def _to_toolcall(tc: dict) -> ToolCall:
    """toolCalls[].functionCall (name + arguments-объект) → нормализованный ToolCall."""
    fc = tc.get("functionCall", {}) or {}
    return ToolCall(function={"name": fc.get("name", ""),
                              "arguments": json.dumps(fc.get("arguments", {}), ensure_ascii=False)})


class YandexGPTAdapter(Adapter):
    name = "yandexgpt"
    supports_seed = False
    supports_tools = True            # function calling (нативный формат Yandex)

    def __init__(self, api_key: str, folder_id: str, base_url: str = _BASE_URL,
                 iam: bool = False, transport=None, timeout: int = 120):
        super().__init__(transport, timeout)
        self.api_key = api_key
        self.folder_id = folder_id
        self.base_url = base_url.rstrip("/")
        self.iam = iam               # True → Bearer (IAM-токен), иначе Api-Key

    def _model_uri(self, model_id: str) -> str:
        # уже полный URI — отдаём как есть, иначе собираем из folder_id
        return model_id if model_id.startswith("gpt://") else f"gpt://{self.folder_id}/{model_id}"

    def chat(self, model_id, messages, *, temperature=0.0, max_tokens=4096,
             seed=None, tools=None, tool_choice="auto") -> LLMResult:
        auth = f"Bearer {self.api_key}" if self.iam else f"Api-Key {self.api_key}"
        headers = {"Authorization": auth, "Content-Type": "application/json",
                   "x-folder-id": self.folder_id}
        body: dict = {
            "modelUri": self._model_uri(model_id),
            "completionOptions": {"temperature": temperature, "maxTokens": str(max_tokens)},
            "messages": [_to_yandex_message(m) for m in messages],
        }
        if tools:                                    # OpenAI-формат tools → формат Yandex
            body["tools"] = [{"function": t["function"]} for t in tools]
            # tool_choice не шлём: Yandex по умолчанию auto, а строкой он ломает запрос
        resp, elapsed, err = self._send("POST", f"{self.base_url}/foundationModels/v1/completion",
                                        headers=headers, json=body)
        if err:
            return LLMResult.failure(f"{self.name}: {err}", elapsed)
        if resp.status_code != 200:
            return LLMResult.failure(http_error(resp), elapsed)
        return self._parse(resp.body, model_id, elapsed)

    @staticmethod
    def _parse(body: dict | None, model_id: str, elapsed: float) -> LLMResult:
        result = (body or {}).get("result", {}) or {}
        alts = result.get("alternatives", []) or []
        content, tool_calls = "", None
        if alts:
            msg = alts[0].get("message", {}) or {}
            content = msg.get("text", "") or ""
            raw_tc = (msg.get("toolCallList", {}) or {}).get("toolCalls") or []
            if raw_tc:
                tool_calls = [_to_toolcall(tc) for tc in raw_tc]
        usage = result.get("usage", {}) or {}
        ti = int(usage.get("inputTextTokens", 0) or 0)
        to = int(usage.get("completionTokens", 0) or 0)
        tt = int(usage.get("totalTokens", 0) or 0) or (ti + to)
        return LLMResult(success=True, content=content, tool_calls=tool_calls,
                         tokens_input=ti, tokens_output=to, tokens_total=tt, elapsed=elapsed,
                         model_used=result.get("modelVersion", model_id), raw=body)
