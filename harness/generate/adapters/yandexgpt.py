"""Адаптер Yandex Cloud Foundation Models (YandexGPT).

Формат запроса/ответа НЕ совпадает с OpenAI, поэтому переводим вручную:
 - запрос: {modelUri, completionOptions:{temperature, maxTokens}, messages:[{role, text}]};
 - ответ:  {result:{alternatives:[{message:{role,text}}], usage:{inputTextTokens,...}}}.
modelUri собирается из folder_id и id модели: gpt://<folder>/<model_id> (например
yandexgpt/latest). Seed не поддерживается; функции пока консервативно выключены.
Авторизация — Api-Key (или IAM-токен).
"""

from __future__ import annotations

from ..types import LLMResult
from .base import Adapter, http_error

_BASE_URL = "https://llm.api.cloud.yandex.net"


class YandexGPTAdapter(Adapter):
    name = "yandexgpt"
    supports_seed = False
    supports_tools = False

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
        body = {
            "modelUri": self._model_uri(model_id),
            "completionOptions": {"temperature": temperature, "maxTokens": str(max_tokens)},
            "messages": [{"role": m.role, "text": m.content} for m in messages],
        }
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
        content = ""
        if alts:
            content = (alts[0].get("message", {}) or {}).get("text", "") or ""
        usage = result.get("usage", {}) or {}
        ti = int(usage.get("inputTextTokens", 0) or 0)
        to = int(usage.get("completionTokens", 0) or 0)
        tt = int(usage.get("totalTokens", 0) or 0) or (ti + to)
        return LLMResult(success=True, content=content, tokens_input=ti, tokens_output=to,
                         tokens_total=tt, elapsed=elapsed,
                         model_used=result.get("modelVersion", model_id), raw=body)
