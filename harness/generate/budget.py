"""Учёт стоимости прогона: живой счётчик с капом + предполётная оценка.

Операционный слой — на баллы SMOP не влияет. CostMeter потокобезопасен: при
параллельной генерации воркеры складывают стоимость под локом. Кап «мягкий» —
вызовы, уже стартовавшие в других потоках, могут немного перелить за порог;
новые пары после превышения не запускаются.
"""

from __future__ import annotations

import threading

from .pricing import PriceTable


class CostMeter:
    """Потокобезопасный счётчик потраченного + порог остановки (max_cost USD)."""

    def __init__(self, max_cost: float | None = None):
        self.max_cost = max_cost
        self._lock = threading.Lock()
        self._spent = 0.0
        self._calls = 0

    def add(self, cost: float) -> None:
        with self._lock:
            self._spent += cost
            self._calls += 1

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls

    def exceeded(self) -> bool:
        """Достигнут ли кап (нет капа → никогда)."""
        if self.max_cost is None:
            return False
        with self._lock:
            return self._spent >= self.max_cost


def estimate_cost(pricing: PriceTable, pairs: list[tuple[str, int]], max_tokens: int) -> dict:
    """Грубая ВЕРХНЯЯ оценка стоимости до прогона.

    pairs — список (id_модели, число_прогонов). На прогон считаем по max_tokens и на
    вход, и на выход (консервативно: реальный вход обычно меньше). Возвращает итог +
    разбивку по моделям + список моделей без цены (бюджет по ним недосчитан).
    """
    by_model: dict[str, float] = {}
    unknown: set[str] = set()
    for model_id, runs in pairs:
        if not pricing.known(model_id):
            unknown.add(model_id)
        _, _, per_run = pricing.cost(model_id, max_tokens, max_tokens)
        by_model[model_id] = by_model.get(model_id, 0.0) + per_run * runs
    return {
        "total": round(sum(by_model.values()), 4),
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
        "unknown_price": sorted(unknown),
        "as_of": pricing.as_of,
    }
