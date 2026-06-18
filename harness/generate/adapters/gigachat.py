"""Адаптер Sber GigaChat: OAuth-токен + OpenAI-совместимый чат.

Две особенности против openai_compat:
 1. Авторизация в два шага — по ключу авторизации (base64 client_id:secret) берётся
    короткоживущий access_token (кэшируется до истечения), им и ходим в чат.
 2. Нет параметра seed (детерминизм только температурой) — supports_seed=False.
Чат-эндпоинт сам по себе OpenAI-формата, поэтому ответ парсится общим parse_openai_chat.

Примечание по сети: GigaChat использует российский корневой сертификат — боевому
транспорту может потребоваться свой CA или RequestsTransport(verify=False).
"""

from __future__ import annotations

import time
import uuid

from ..types import LLMResult
from .base import Adapter, http_error
from .openai_compat import parse_openai_chat

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"


class GigaChatAdapter(Adapter):
    name = "gigachat"
    supports_seed = False
    supports_tools = True  # GigaChat поддерживает функции

    def __init__(
        self,
        auth_key: str,
        scope: str = "GIGACHAT_API_PERS",
        base_url: str = _BASE_URL,
        oauth_url: str = _OAUTH_URL,
        transport=None,
        timeout: int = 120,
    ):
        super().__init__(transport, timeout)
        self.auth_key = auth_key
        self.scope = scope
        self.base_url = base_url.rstrip("/")
        self.oauth_url = oauth_url
        self._token: str | None = None
        self._token_exp_ms: float = 0.0  # epoch ms истечения токена

    def _ensure_token(self) -> tuple[str | None, str | None]:
        """Действующий access_token (с кэшем). Возврат (токен|None, ошибка|None)."""
        if self._token and time.time() * 1000 < self._token_exp_ms - 60_000:
            return self._token, None
        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        resp, _, err = self._send(
            "POST", self.oauth_url, headers=headers, data={"scope": self.scope}
        )
        if err:
            return None, f"{self.name} oauth: {err}"
        if resp.status_code != 200:
            return None, f"{self.name} oauth: {http_error(resp)}"
        body = resp.body or {}
        self._token = body.get("access_token")
        self._token_exp_ms = float(body.get("expires_at", 0) or 0)
        if not self._token:
            return None, f"{self.name} oauth: нет access_token в ответе"
        return self._token, None

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
        token, err = self._ensure_token()
        if err:
            return LLMResult.failure(err)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body: dict = {
            "model": model_id,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # seed не поддерживается — сознательно не отправляем (см. supports_seed)
        if tools:
            body["functions"] = tools

        resp, elapsed, err = self._send(
            "POST", f"{self.base_url}/chat/completions", headers=headers, json=body
        )
        if err:
            return LLMResult.failure(f"{self.name}: {err}", elapsed)
        if resp.status_code != 200:
            return LLMResult.failure(http_error(resp), elapsed)
        return parse_openai_chat(resp.body, model_id, elapsed)
