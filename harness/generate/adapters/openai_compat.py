"""OpenAI-совместимый адаптер — lingua franca.

Покрывает облако (OpenRouter: Claude/GPT/Gemini) и локальные серверы
(Ollama, vLLM, LM Studio) — у них один протокол `/chat/completions`, отличаются
лишь base_url и наличием ключа. Поддерживает seed и tools (фактически — по модели).
"""

from __future__ import annotations

from ..types import LLMResult, ToolCall
from .base import Adapter, http_error


def parse_openai_chat(body: dict | None, model_id: str, elapsed: float) -> LLMResult:
    """Ответ OpenAI-формата → LLMResult (используется и GigaChat — формат тот же)."""
    body = body or {}
    choices = body.get("choices", []) or []
    content, tool_calls = "", None
    if choices:
        msg = choices[0].get("message", {}) or {}
        content = msg.get("content") or ""
        raw_tc = msg.get("tool_calls")
        if raw_tc:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    type=tc.get("type", "function"),
                    function=tc.get("function", {}),
                )
                for tc in raw_tc
            ]
    usage = body.get("usage", {}) or {}
    # Детализация usage: reasoning сидит внутри completion_tokens, кеш — внутри prompt_tokens.
    # Отдают не все провайдеры, поэтому всё через .get с нулём.
    pd = usage.get("prompt_tokens_details") or {}
    cd = usage.get("completion_tokens_details") or {}
    choice = choices[0] if choices else {}
    msg = choice.get("message", {}) or {}
    return LLMResult(
        success=True,
        content=content,
        tool_calls=tool_calls,
        tokens_input=usage.get("prompt_tokens", 0),
        tokens_output=usage.get("completion_tokens", 0),
        tokens_total=usage.get("total_tokens", 0),
        tokens_reasoning=cd.get("reasoning_tokens", 0) or 0,
        tokens_cached=pd.get("cached_tokens", 0) or 0,
        tokens_cache_write=pd.get("cache_write_tokens", 0) or 0,
        reasoning=msg.get("reasoning") or "",
        finish_reason=choice.get("finish_reason") or "",
        system_fingerprint=body.get("system_fingerprint") or "",
        cost_reported=usage.get("cost_rub"),
        elapsed=elapsed,
        model_used=body.get("model", model_id),
        raw=body,
    )


class OpenAICompatAdapter(Adapter):
    name = "openai_compat"
    supports_seed = True
    supports_tools = True

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        transport=None,
        timeout: int = 120,
        extra_headers: dict | None = None,
        reasoning_effort: str | None = None,
    ):
        super().__init__(transport, timeout)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        # уровень рассуждений (none|low|medium|high|xhigh|max) — ручка КАНАЛА, не факт о модели:
        # у одного SKU провайдера бывает несколько режимов. None → поле в тело не попадает,
        # запрос прежних моделей не меняется.
        self.reasoning_effort = reasoning_effort

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
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict = {
            "model": model_id,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.reasoning_effort:  # набор значений гейтит prism check
            body["reasoning_effort"] = self.reasoning_effort
        if seed is not None:
            body["seed"] = seed
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice

        resp, elapsed, err = self._send(
            "POST", f"{self.base_url}/chat/completions", headers=headers, json=body
        )
        if err:
            return LLMResult.failure(f"{self.name}: {err}", elapsed)
        if resp.status_code != 200:
            return LLMResult.failure(http_error(resp), elapsed)
        return parse_openai_chat(resp.body, model_id, elapsed)
