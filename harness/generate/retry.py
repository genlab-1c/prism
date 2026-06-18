"""Повтор вызова модели при транзиентном сбое сети.

Адаптер ловит сетевое исключение в LLMResult(success=False, error=...) и не падает;
здесь — решение «повторять или нет» по тексту ошибки (адаптер остаётся «глупым»,
статус-код уже зашит в error строкой http_error).

Классификация по строке, а не по типу: транзиентное (429/5xx/таймаут/обрыв) —
повторяем с экспоненциальной паузой; перманентное (401/403/нет кредитов/битый ключ) —
сразу отдаём, повтор бессмыслен. sleep инъектируется → тесты без реального ожидания.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from .types import LLMResult

# подстроки в тексте ошибки (lower-case). Перманентные проверяются первыми.
_PERMANENT = (
    "401",
    "403",
    "invalid api key",
    "insufficient",
    "quota exceeded",
    "unauthorized",
    "forbidden",
)
_TRANSIENT = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "temporar",
    "overload",
    "rate limit",
    "unavailable",
    "reset",
)


def is_transient(error: str | None) -> bool:
    """Стоит ли повторять вызов с такой ошибкой."""
    e = (error or "").lower()
    if any(m in e for m in _PERMANENT):
        return False
    return any(m in e for m in _TRANSIENT)


def with_retry(
    call: Callable[[], LLMResult],
    *,
    retries: int = 3,
    base_delay: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, str | None, float], None] | None = None,
) -> LLMResult:
    """Вызвать call(); при транзиентном фейле повторить до retries раз с бэкоффом.

    Возвращает первый успех либо последний фейл (исчерпали попытки / ошибка перманентна).
    base_delay * 2**attempt — экспоненциальная пауза (2, 4, 8, ...).
    """
    last = LLMResult.failure("вызов не выполнен")
    for attempt in range(retries + 1):
        last = call()
        if last.success:
            return last
        if attempt >= retries or not is_transient(last.error):
            break
        delay = base_delay * (2**attempt)
        if on_retry:
            on_retry(attempt + 1, last.error, delay)
        sleep(delay)
    return last
