"""Тесты слоя адаптеров — офлайн, через фейковый транспорт (без сети и ключей).

Проверяем: нормализацию ответа в LLMResult, корректность тела/заголовков запроса,
провайдер-специфику (OAuth GigaChat, формат YandexGPT), обработку ошибок и таймаутов,
выбор адаптера реестром и объявленные возможности (seed/tools).
"""

from __future__ import annotations

import json

import pytest

from harness.generate.adapters import (
    AdapterConfigError,
    GigaChatAdapter,
    OpenAICompatAdapter,
    YandexGPTAdapter,
    YandexResponsesAdapter,
    build_adapter,
)
from harness.generate.adapters.registry import ADAPTERS
from harness.generate.transport import HttpResponse
from harness.generate.types import ChatMessage, ToolCall


class FakeTransport:
    """Транспорт-заглушка: отдаёт заранее заготовленные ответы по очереди, пишет запросы."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []  # список dict(method,url,headers,json,data)

    def request(self, method, url, *, headers, json=None, data=None, timeout=120):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "data": data}
        )
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def ok(body):
    return HttpResponse(200, body, json.dumps(body))


MSGS = [ChatMessage.system("ты пишешь BSL"), ChatMessage.user("сделай функцию")]


# ── типы ──────────────────────────────────────────────────────────────────────


def test_chatmessage_to_openai_with_tool_call():
    tc = ToolCall(id="c1", function={"name": "get", "arguments": "{}"})
    asst = ChatMessage.assistant("", tool_calls=[tc])
    d = asst.to_openai()
    assert d["role"] == "assistant"
    assert d["tool_calls"][0]["id"] == "c1"
    tr = ChatMessage.tool_response("результат", tool_call_id="c1", name="get").to_openai()
    assert tr["role"] == "tool" and tr["tool_call_id"] == "c1" and tr["name"] == "get"


# ── openai_compat (OpenRouter / локаль) ────────────────────────────────────────


def test_openai_compat_parses_content_and_usage():
    t = FakeTransport(
        [
            ok(
                {
                    "model": "m",
                    "choices": [{"message": {"content": "Функция Ф() КонецФункции"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                }
            )
        ]
    )
    a = OpenAICompatAdapter("http://x/v1", api_key="k", transport=t)
    r = a.chat("m", MSGS, seed=42, temperature=0.0)
    assert r.success and r.content.startswith("Функция")
    assert (r.tokens_input, r.tokens_output, r.tokens_total) == (10, 20, 30)
    body = t.calls[0]["json"]
    assert body["seed"] == 42  # seed уходит
    assert body["messages"][0] == {"role": "system", "content": "ты пишешь BSL"}
    assert t.calls[0]["headers"]["Authorization"] == "Bearer k"
    assert t.calls[0]["url"].endswith("/chat/completions")


def test_openai_compat_tool_calls_parsed():
    t = FakeTransport(
        [
            ok(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "x1",
                                        "type": "function",
                                        "function": {"name": "поиск", "arguments": '{"q":1}'},
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {},
                }
            )
        ]
    )
    a = OpenAICompatAdapter("http://x/v1", transport=t)
    r = a.chat("m", MSGS, tools=[{"type": "function", "function": {"name": "поиск"}}])
    assert r.tool_calls and r.tool_calls[0].name == "поиск"
    assert t.calls[0]["json"]["tools"]  # tools уходят
    assert "Authorization" not in t.calls[0]["headers"]  # локаль без ключа


def test_openai_compat_http_error_and_network_error():
    a = OpenAICompatAdapter(
        "http://x/v1",
        transport=FakeTransport([HttpResponse(429, {"error": {"message": "rate limit"}}, "")]),
    )
    r = a.chat("m", MSGS)
    assert not r.success and "429" in r.error and "rate limit" in r.error

    a2 = OpenAICompatAdapter("http://x/v1", transport=FakeTransport([TimeoutError("таймаут")]))
    r2 = a2.chat("m", MSGS)
    assert not r2.success and "таймаут" in r2.error


# ── GigaChat (OAuth + чат) ──────────────────────────────────────────────────────


def test_gigachat_oauth_then_chat_and_token_cache():
    t = FakeTransport(
        [
            ok({"access_token": "TOK", "expires_at": 9_999_999_999_000}),  # oauth
            ok(
                {"choices": [{"message": {"content": "ок"}}], "usage": {"total_tokens": 5}}
            ),  # chat 1
            ok(
                {"choices": [{"message": {"content": "ещё"}}], "usage": {"total_tokens": 7}}
            ),  # chat 2
        ]
    )
    a = GigaChatAdapter(auth_key="BASE64", transport=t)
    r1 = a.chat("GigaChat", MSGS, seed=42)  # seed должен быть проигнорирован
    assert r1.success and r1.content == "ок"
    # 1-й запрос — oauth (form-data scope), 2-й — чат (Bearer токен, без seed)
    assert t.calls[0]["data"] == {"scope": "GIGACHAT_API_PERS"}
    assert "RqUID" in t.calls[0]["headers"]
    assert t.calls[1]["headers"]["Authorization"] == "Bearer TOK"
    assert "seed" not in t.calls[1]["json"]
    r2 = a.chat("GigaChat", MSGS)  # токен в кэше → нет нового oauth
    assert r2.success and len(t.calls) == 3  # oauth(1) + chat(2)
    assert a.supports_seed is False


def test_gigachat_oauth_failure():
    a = GigaChatAdapter(
        auth_key="BAD",
        transport=FakeTransport([HttpResponse(401, {"message": "unauthorized"}, "")]),
    )
    r = a.chat("GigaChat", MSGS)
    assert not r.success and "oauth" in r.error and "401" in r.error


# ── YandexGPT (свой формат) ─────────────────────────────────────────────────────


def test_yandexgpt_request_format_and_parse():
    t = FakeTransport(
        [
            ok(
                {
                    "result": {
                        "alternatives": [
                            {"message": {"role": "assistant", "text": "Функция Я() КонецФункции"}}
                        ],
                        "usage": {
                            "inputTextTokens": "12",
                            "completionTokens": "8",
                            "totalTokens": "20",
                        },
                        "modelVersion": "rc1",
                    }
                }
            )
        ]
    )
    a = YandexGPTAdapter(api_key="K", folder_id="fld", transport=t)
    r = a.chat("yandexgpt/latest", MSGS, temperature=0.3)
    assert r.success and r.content.startswith("Функция Я")
    assert (r.tokens_input, r.tokens_output, r.tokens_total) == (12, 8, 20)
    body = t.calls[0]["json"]
    assert body["modelUri"] == "gpt://fld/yandexgpt/latest"
    assert body["messages"][1] == {"role": "user", "text": "сделай функцию"}  # формат text
    assert body["completionOptions"]["temperature"] == 0.3
    assert t.calls[0]["headers"]["Authorization"] == "Api-Key K"
    assert a.supports_seed is False and a.supports_tools is True


def test_yandexgpt_tools_request_and_toolcall_parse():
    """Function calling: tools в формат Yandex, ответный toolCallList → tool_calls."""
    t = FakeTransport(
        [
            ok(
                {
                    "result": {
                        "alternatives": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "toolCallList": {
                                        "toolCalls": [
                                            {
                                                "functionCall": {
                                                    "name": "get_object_structure",
                                                    "arguments": {
                                                        "name": "Справочник.Номенклатура"
                                                    },
                                                }
                                            }
                                        ]
                                    },
                                }
                            }
                        ],
                        "usage": {
                            "inputTextTokens": "5",
                            "completionTokens": "3",
                            "totalTokens": "8",
                        },
                    }
                }
            )
        ]
    )
    a = YandexGPTAdapter(api_key="K", folder_id="fld", transport=t)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_object_structure",
                "description": "структура",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    r = a.chat("aliceai-llm/latest", MSGS, tools=tools)
    body = t.calls[0]["json"]
    assert body["tools"] == [{"function": tools[0]["function"]}]  # OpenAI → формат Yandex
    assert "tool_choice" not in body  # строкой ломает Yandex
    assert r.tool_calls and r.tool_calls[0].name == "get_object_structure"
    assert json.loads(r.tool_calls[0].arguments_raw) == {"name": "Справочник.Номенклатура"}


def test_yandexgpt_serializes_tool_messages():
    """assistant-с-вызовами и tool-результат → нативные toolCallList / toolResultList."""
    t = FakeTransport(
        [
            ok(
                {
                    "result": {
                        "alternatives": [{"message": {"role": "assistant", "text": "ок"}}],
                        "usage": {},
                    }
                }
            )
        ]
    )
    a = YandexGPTAdapter(api_key="K", folder_id="fld", transport=t)
    msgs = [
        ChatMessage.user("задача"),
        ChatMessage.assistant(
            "", tool_calls=[ToolCall(function={"name": "f", "arguments": '{"x": 1}'})]
        ),
        ChatMessage.tool_response("результат", tool_call_id="1", name="f"),
    ]
    a.chat("aliceai-llm/latest", msgs)
    sent = t.calls[0]["json"]["messages"]
    assert sent[1] == {
        "role": "assistant",
        "toolCallList": {"toolCalls": [{"functionCall": {"name": "f", "arguments": {"x": 1}}}]},
    }  # arguments — ОБЪЕКТ
    assert sent[2] == {
        "role": "assistant",
        "toolResultList": {
            "toolResults": [{"functionResult": {"name": "f", "content": "результат"}}]
        },
    }


# ── registry ────────────────────────────────────────────────────────────────────


def test_registry_builds_each_adapter_from_env():
    env = {
        "OPENROUTER_API_KEY": "or",
        "GIGACHAT_AUTH_KEY": "gc",
        "YANDEX_API_KEY": "yk",
        "YANDEX_FOLDER_ID": "fld",
    }
    assert isinstance(build_adapter("openrouter", env=env), OpenAICompatAdapter)
    assert isinstance(build_adapter("gigachat", env=env), GigaChatAdapter)
    assert isinstance(build_adapter("yandexgpt", env=env), YandexGPTAdapter)
    assert isinstance(build_adapter("yandex_responses", env=env), YandexResponsesAdapter)
    local = build_adapter("openai_compat", endpoint="http://localhost:11434/v1", env={})
    assert isinstance(local, OpenAICompatAdapter) and local.base_url.endswith("11434/v1")


def test_registry_missing_creds_and_unknown_adapter():
    with pytest.raises(AdapterConfigError):
        build_adapter("openrouter", env={})  # нет ключа
    with pytest.raises(AdapterConfigError):
        build_adapter("openai_compat", env={})  # нет endpoint
    with pytest.raises(AdapterConfigError):
        build_adapter("несуществующий", env={})
    assert set(ADAPTERS) == {
        "openrouter",
        "openai_compat",
        "gigachat",
        "yandexgpt",
        "yandex_responses",
    }


def test_registry_proxy_selected_by_adapter_group():
    """RU-прокси → Yandex/GigaChat, INTL-прокси → OpenRouter; локальный — без прокси."""
    env = {
        "OPENROUTER_API_KEY": "or",
        "GIGACHAT_AUTH_KEY": "gc",
        "YANDEX_API_KEY": "yk",
        "YANDEX_FOLDER_ID": "fld",
        "PRISM_PROXY_RU": "http://ru-proxy:3128",
        "PRISM_PROXY_INTL": "http://intl-proxy:3128",
    }
    ru = {"http": "http://ru-proxy:3128", "https": "http://ru-proxy:3128"}
    intl = {"http": "http://intl-proxy:3128", "https": "http://intl-proxy:3128"}
    assert build_adapter("yandex_responses", env=env).transport.proxies == ru
    assert build_adapter("yandexgpt", env=env).transport.proxies == ru
    assert build_adapter("gigachat", env=env).transport.proxies == ru
    assert build_adapter("openrouter", env=env).transport.proxies == intl
    # без прокси-переменных транспорт не подменяется (proxies отсутствуют/None)
    bare = build_adapter("yandexgpt", env={"YANDEX_API_KEY": "k", "YANDEX_FOLDER_ID": "f"})
    assert getattr(bare.transport, "proxies", None) is None
