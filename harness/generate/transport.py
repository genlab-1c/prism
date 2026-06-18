"""HTTP-транспорт слоя адаптеров — инъектируемый ради тестируемости.

Адаптеры зовут не `requests` напрямую, а Transport.request(): в тестах подставляется
фейковый транспорт с готовыми ответами — без сети, без ключей, без зависимости от
requests на этапе импорта (requests импортируется лениво только в боевом транспорте).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class HttpResponse:
    """Нормализованный HTTP-ответ: код + распарсенный JSON (или None) + сырой текст."""

    status_code: int
    body: Any = None  # распарсенный JSON (dict/list) либо None
    text: str = ""


class Transport(Protocol):
    """Контракт транспорта. method: GET|POST; json — тело JSON, data — форма (x-www-form)."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        data: dict | None = None,
        timeout: int = 120,
    ) -> HttpResponse: ...


class RequestsTransport:
    """Боевой транспорт на requests. verify=False бывает нужен GigaChat (российский CA)."""

    def __init__(self, verify: bool = True):
        self.verify = verify

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        data: dict | None = None,
        timeout: int = 120,
    ) -> HttpResponse:
        import requests  # ленивый импорт: тесты с фейк-транспортом requests не требуют

        resp = requests.request(
            method, url, headers=headers, json=json, data=data, timeout=timeout, verify=self.verify
        )
        try:
            body = resp.json()
        except ValueError:
            body = None
        return HttpResponse(resp.status_code, body, resp.text)


default_transport: Transport = RequestsTransport()
