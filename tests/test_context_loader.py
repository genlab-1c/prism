"""Тесты агентного context loader — офлайн, на сценарном фейк-адаптере (без сети/ключей).

Адаптер отдаёт заранее заготовленную цепочку tool-calls; провайдер настоящий
(SpecMetadataProvider над маленьким спеком). Проверяем: сбор контекста по
get_object_structure, завершение по finish_research, лимит объектов, отсутствие
tool_calls = досрочный конец, сбой адаптера, и что игнор «не найден» не попадает в контекст.
"""

from __future__ import annotations

import json

from harness.generate.context import AgenticContextLoader, SpecMetadataProvider
from harness.generate.types import LLMResult, ToolCall

SPEC = {
    "catalogs": {"Склады": {"hierarchical": False}, "Номенклатура": {"hierarchical": True}},
    "accumulation_registers": {
        "ТоварыНаСкладах": {"register_type": "Balance",
                            "dimensions": {"Склад": {"type": "СправочникСсылка.Склады"}},
                            "resources": {"ВНаличии": {"type": "Число", "length": 15, "precision": 3}}}},
}


def _tc(call_id: str, tool: str, **args) -> ToolCall:
    return ToolCall(id=call_id, function={"name": tool, "arguments": json.dumps(args)})


class ScriptedAdapter:
    """Фейк-адаптер: отдаёт LLMResult из очереди, игнорируя вход; считает вызовы."""

    name = "scripted"
    supports_seed = True
    supports_tools = True

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def chat(self, model_id, messages, **kw) -> LLMResult:
        self.calls += 1
        return self._script.pop(0)


def _result(tool_calls=None, content="", ok=True, tokens=10):
    return LLMResult(success=ok, content=content, tool_calls=tool_calls,
                     tokens_total=tokens, error=None if ok else "boom")


def test_agent_collects_structure_then_finishes():
    adapter = ScriptedAdapter([
        _result([_tc("a", "search_objects", query="товар")]),
        _result([_tc("b", "get_object_structure", name="РегистрНакопления.ТоварыНаСкладах")]),
        _result([_tc("c", "finish_research", summary="беру ТоварыНаСкладах")]),
    ])
    loader = AgenticContextLoader(adapter, SpecMetadataProvider(SPEC), "model")
    r = loader.load("получить остатки")
    assert r.success and r.iterations == 3 and r.tool_calls == 3
    assert r.objects_loaded == ["РегистрНакопления.ТоварыНаСкладах"]
    assert "вид: остатки" in r.context_text and "ВНаличии (Число 15.3)" in r.context_text
    assert r.summary == "беру ТоварыНаСкладах"
    assert r.tokens == 30


def test_max_objects_limit_stops_early():
    adapter = ScriptedAdapter([
        _result([_tc("1", "get_object_structure", name="Склады")]),
        _result([_tc("2", "get_object_structure", name="Номенклатура")]),
        _result([_tc("3", "get_object_structure", name="ТоварыНаСкладах")]),  # не дойдём
    ])
    loader = AgenticContextLoader(adapter, SpecMetadataProvider(SPEC), "model", max_objects=2)
    r = loader.load("задача")
    assert len(r.objects_loaded) == 2 and adapter.calls == 2     # остановились на лимите


def test_no_tool_calls_ends_loop():
    adapter = ScriptedAdapter([_result(content="готов писать код", tool_calls=None)])
    r = AgenticContextLoader(adapter, SpecMetadataProvider(SPEC), "model").load("задача")
    assert r.success and r.objects_loaded == [] and r.context_text == ""


def test_unknown_object_not_added_to_context():
    adapter = ScriptedAdapter([
        _result([_tc("x", "get_object_structure", name="ВымышленныйРегистр")]),
        _result([_tc("y", "finish_research", summary="ничего не нашёл")]),
    ])
    r = AgenticContextLoader(adapter, SpecMetadataProvider(SPEC), "model").load("задача")
    assert r.objects_loaded == [] and r.context_text == ""       # «не найден» в контекст не идёт


def test_adapter_failure_propagates():
    adapter = ScriptedAdapter([_result(ok=True, tool_calls=None) if False else _result(ok=False)])
    r = AgenticContextLoader(adapter, SpecMetadataProvider(SPEC), "model").load("задача")
    assert not r.success and r.error == "boom"
