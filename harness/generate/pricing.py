"""Стоимость прогона по датированной таблице цен (generation/pricing.yaml).

Цены — волатильные данные, поэтому отдельной датированной таблицей, а не в каталоге
моделей. Это операционный слой (учёт денег), он НЕ влияет на баллы SMOP: метрика
считается из ответов модели, а не из их стоимости.

Модель без цены → стоимость 0 + флаг known()=False (раннер предупредит). Так бюджет
честно недосчитан, а не врёт фиктивным числом.
"""

from __future__ import annotations

import yaml
from pydantic import BaseModel

from harness.loaders import PRISM

_PER = 1_000_000          # цены публикуют за 1М токенов


class PriceTable(BaseModel):
    """Снимок цен: дата + {id модели: {input, output}} USD за 1М токенов."""

    as_of: str = ""
    source: str = ""
    prices: dict[str, dict[str, float]] = {}

    def known(self, model_id: str) -> bool:
        return model_id in self.prices

    def cost(self, model_id: str, tokens_input: int, tokens_output: int) -> tuple[float, float, float]:
        """(стоимость_вход, стоимость_выход, итого) в USD. Нет цены → нули."""
        p = self.prices.get(model_id)
        if not p:
            return 0.0, 0.0, 0.0
        ci = tokens_input / _PER * p.get("input", 0.0)
        co = tokens_output / _PER * p.get("output", 0.0)
        return ci, co, ci + co


def load_pricing(root: object = PRISM) -> PriceTable:
    path = root / "generation" / "pricing.yaml"          # type: ignore[operator]
    if not path.exists():
        return PriceTable()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PriceTable(**{k: data[k] for k in ("as_of", "source", "prices") if k in data})
