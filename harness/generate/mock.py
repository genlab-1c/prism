"""Сборка сухого прогона генерации (prism generate --mock) — без сети и ключей.

Подменяет каталог моделей одной синтетической `mock/echo` и фабрику адаптеров на
MockAdapter. Остальной конвейер (контекст B, чекпойнт, запись experiment_*.json,
хеши, детерминизм) идёт штатно — поэтому потом работает обычный `prism score`.
"""

from __future__ import annotations

from harness.generate.adapters.mock import MockAdapter
from harness.generate.pricing import PriceTable
from harness.generate.run import GenerationRunner
from harness.loaders import ModelAccess, ModelEntry, load_generation, load_tasks

MOCK_KEY = "mock"
MOCK_ID = "mock/echo"

# Заглушка для mode=stub: синтаксически целый, но бессодержательный код — показывает,
# как выглядит «провальный» прогон (низкие M/O), не падая на компиляции.
_STUB = "```bsl\n// заглушка mock — решение не реализовано\nФункция Решение()\n    Возврат Неопределено;\nКонецФункции\n```"


def _responses(mode: str) -> dict[str, str]:
    """{промпт задачи: ответ}. mode=canonical → эталон задачи; иначе пусто (всё в stub)."""
    if mode != "canonical":
        return {}
    out: dict[str, str] = {}
    for t in load_tasks():
        if t.canonical is not None:
            code = t.canonical.read_text(encoding="utf-8-sig").strip()
            out[t.prompt] = f"```bsl\n{code}\n```"
    return out


def build_mock_runner(mode: str = "canonical", *, verbose: bool = True) -> GenerationRunner:
    """GenerationRunner поверх синтетической модели mock/echo (offline)."""
    gen = load_generation()
    entry = ModelEntry(
        id=MOCK_ID,
        name=f"mock ({'эталон' if mode == 'canonical' else 'заглушка'})",
        vendor="mock",
        access=ModelAccess(adapter="mock"),
        capabilities={"supports_tools": False, "supports_seed": False, "context_window": 32000},
    )
    responses = _responses(mode)
    factory = lambda key, e: MockAdapter(responses, stub=_STUB)  # noqa: E731 — короткая фабрика
    params = {**gen.params, "model_params": {MOCK_KEY: {"runs": 1, "temperature": 0.0}}}
    pricing = PriceTable(prices={MOCK_ID: {"input": 0.0, "output": 0.0}})  # стоимость = 0, без warn
    return GenerationRunner(
        adapter_factory=factory,
        models={MOCK_KEY: entry},
        params=params,
        pricing=pricing,
        verbose=verbose,
    )
