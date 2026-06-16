"""Операционный слой генерации: прайс, бюджет, ретраи — чистая логика, офлайн.

Чекпойнт/resume/кап на раннере — в test_generate_run.py (там сценарный адаптер).
"""

from __future__ import annotations

from harness.generate.budget import CostMeter, estimate_cost
from harness.generate.pricing import PriceTable, load_pricing
from harness.generate.retry import is_transient, with_retry
from harness.generate.types import LLMResult


# ── прайс ──────────────────────────────────────────────────────────────────

def _table() -> PriceTable:
    return PriceTable(as_of="2026-06-16", prices={
        "m/known": {"input": 3.0, "output": 15.0}})


def test_cost_math():
    t = _table()
    ci, co, ct = t.cost("m/known", 1_000_000, 2_000_000)   # 1М вход × $3 + 2М выход × $15
    assert ci == 3.0 and co == 30.0 and ct == 33.0


def test_cost_unknown_model_is_zero():
    t = _table()
    assert t.known("m/known") and not t.known("m/missing")
    assert t.cost("m/missing", 10**6, 10**6) == (0.0, 0.0, 0.0)


def test_real_pricing_table_loads():
    """Файл generation/pricing.yaml валиден и покрывает модели каталога."""
    t = load_pricing()
    assert t.as_of, "у снимка цен нет даты"
    from harness.loaders import load_generation
    for key, m in load_generation().models.items():
        assert t.known(m.id), f"нет цены для {key} ({m.id}) в pricing.yaml"


# ── бюджет ───────────────────────────────────────────────────────────────────

def test_cost_meter_accumulates_and_caps():
    m = CostMeter(max_cost=1.0)
    assert not m.exceeded()
    m.add(0.4)
    assert not m.exceeded() and abs(m.spent - 0.4) < 1e-9
    m.add(0.6)
    assert m.exceeded() and m.calls == 2          # 0.4+0.6 = 1.0 ≥ кап


def test_cost_meter_no_cap_never_exceeds():
    m = CostMeter(max_cost=None)
    m.add(10**6)
    assert not m.exceeded()


def test_estimate_flags_unknown_price():
    t = _table()
    est = estimate_cost(t, [("m/known", 2), ("m/missing", 1)], max_tokens=1_000_000)
    # known: 2 прогона × (1М×3 + 1М×15) = 2×18 = 36
    assert est["by_model"]["m/known"] == 36.0
    assert est["unknown_price"] == ["m/missing"]
    assert est["as_of"] == "2026-06-16"


# ── ретраи ─────────────────────────────────────────────────────────────────

def test_is_transient_classification():
    assert is_transient("HTTP 429: rate limit")
    assert is_transient("HTTP 503: unavailable")
    assert is_transient("Connection reset by peer")
    assert is_transient("read timed out")
    assert not is_transient("HTTP 401: invalid api key")
    assert not is_transient("HTTP 400: bad request")     # не в транзиентных → не повторяем
    assert not is_transient(None)


def test_with_retry_recovers_after_transient():
    calls, slept = [], []
    script = [LLMResult.failure("HTTP 503: unavailable"),
              LLMResult.failure("HTTP 429: rate limit"),
              LLMResult(success=True, content="ok")]

    def call():
        calls.append(1)
        return script.pop(0)

    res = with_retry(call, retries=3, base_delay=1.0, sleep=slept.append)
    assert res.success and res.content == "ok"
    assert len(calls) == 3
    assert slept == [1.0, 2.0]            # экспоненциальный бэкофф между попытками


def test_with_retry_no_retry_on_permanent():
    calls, slept = [], []

    def call():
        calls.append(1)
        return LLMResult.failure("HTTP 401: invalid api key")

    res = with_retry(call, retries=5, base_delay=1.0, sleep=slept.append)
    assert not res.success and len(calls) == 1 and slept == []   # перманентная → без повторов


def test_with_retry_exhausts_and_returns_last():
    calls, slept = [], []

    def call():
        calls.append(1)
        return LLMResult.failure("HTTP 503: unavailable")

    res = with_retry(call, retries=2, base_delay=1.0, sleep=slept.append)
    assert not res.success and len(calls) == 3 and slept == [1.0, 2.0]  # 1 + 2 повтора
