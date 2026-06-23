"""Предполётные проверки (doctor/ping) — офлайн, на подменённом каталоге и адаптере."""

from __future__ import annotations

from harness import preflight
from harness.generate.types import LLMResult
from harness.loaders import Generation, ModelAccess, ModelEntry


def _gen() -> Generation:
    """Каталог из двух каналов: openrouter (нужен ключ) и openai_compat (ключ не нужен)."""
    return Generation(
        models={
            "deepseek": ModelEntry(
                id="ds/x",
                name="DeepSeek",
                vendor="deepseek",
                access=ModelAccess(adapter="openrouter"),
                capabilities={},
            ),
            "local": ModelEntry(
                id="local/x",
                name="Local",
                vendor="me",
                access=ModelAccess(adapter="openai_compat", endpoint="http://localhost"),
                capabilities={},
            ),
        },
        params={},
        prompts={},
    )


def test_keys_section_ok_when_key_present(monkeypatch):
    monkeypatch.setattr(preflight, "load_generation", _gen)
    monkeypatch.setattr(preflight, "credentials_env", lambda: {"OPENROUTER_API_KEY": "x"})
    section, any_ready = preflight._keys_section()
    statuses = {st for st, _ in section["items"]}
    assert any_ready is True
    assert "warn" not in statuses  # есть ключ openrouter + локальный канал без ключа


def test_keys_section_warns_when_key_missing(monkeypatch):
    monkeypatch.setattr(preflight, "load_generation", _gen)
    monkeypatch.setattr(preflight, "credentials_env", lambda: {})  # ключей нет
    section, any_ready = preflight._keys_section()
    texts = " ".join(t for _, t in section["items"])
    assert any_ready is True  # openai_compat не требует ключа → канал доступен
    assert "OPENROUTER_API_KEY" in texts  # про отсутствующий ключ предупредили


def test_ping_ok_skip_and_fail(monkeypatch):
    monkeypatch.setattr(preflight, "load_generation", _gen)
    # ключ есть только у openrouter → openai_compat (ключ не нужен) тоже идёт в запрос
    monkeypatch.setattr(preflight, "credentials_env", lambda: {"OPENROUTER_API_KEY": "x"})

    class _Adapter:
        def chat(self, *a, **k):
            return LLMResult(success=True, content="1", elapsed=0.3)

    monkeypatch.setattr(preflight, "build_adapter", lambda *a, **k: _Adapter())
    results = {r["key"]: r for r in preflight.ping_models()}
    assert results["deepseek"]["status"] == "ok"
    assert results["local"]["status"] == "ok"

    # сбой канала → fail, команда не падает
    def _boom(*a, **k):
        raise RuntimeError("сеть упала")

    monkeypatch.setattr(preflight, "build_adapter", _boom)
    results = {r["key"]: r for r in preflight.ping_models()}
    assert results["deepseek"]["status"] == "fail"


def test_ping_skips_keyless_model_without_building_adapter(monkeypatch):
    monkeypatch.setattr(preflight, "load_generation", _gen)
    monkeypatch.setattr(preflight, "credentials_env", lambda: {})  # ни одного ключа

    built: list[str] = []

    class _Adapter:
        def chat(self, model_id, *a, **k):
            built.append(model_id)
            return LLMResult(success=True, content="1", elapsed=0.1)

    monkeypatch.setattr(preflight, "build_adapter", lambda *a, **k: _Adapter())
    results = {r["key"]: r for r in preflight.ping_models()}
    # deepseek (openrouter) без ключа → skip и БЕЗ построения адаптера
    assert results["deepseek"]["status"] == "skip"
    assert "ds/x" not in built
    # local (openai_compat) ключа не требует → запрос делается
    assert results["local"]["status"] == "ok"
