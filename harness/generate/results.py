"""Схема результатов генерации — совпадает с тем, что читает скорер (orchestrate.run).

Это шов между слоями: генерация пишет results/experiment_*.json в этой схеме, скорер
её потребляет без изменений. Поэтому ключи и вложенность важны (см. существующие файлы).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunResult(BaseModel):
    """Один прогон генерации (task × model × run)."""

    run_index: int
    seed: int | None = None
    temperature: float = 0.0
    response: str = ""
    response_hash: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    elapsed_time: float = 0.0
    cost_input: float = 0.0
    cost_output: float = 0.0
    cost_total: float = 0.0
    success: bool = True
    error: str | None = None


class DeterminismResult(BaseModel):
    """Детерминизм по прогонам одной пары (задача, модель)."""

    total_runs: int
    unique_responses: int
    match_rate: float
    most_common_hash: str = ""
    most_common_count: int = 0
    hashes: list[str] = Field(default_factory=list)

    @property
    def match_percent(self) -> float:
        return round(self.match_rate * 100, 1)

    @property
    def is_deterministic(self) -> bool:
        return self.unique_responses <= 1 and self.total_runs > 0


class TaskResult(BaseModel):
    """Результат одной пары (задача, модель): все прогоны + детерминизм + контекст."""

    task_id: str
    task_name: str
    model_id: str
    model_name: str
    context_loaded: bool = False
    context_objects: list[str] = Field(default_factory=list)
    context_analysis_cost: float = 0.0
    runs: list[RunResult] = Field(default_factory=list)
    determinism: DeterminismResult | None = None
    total_tokens: int = 0
    total_cost: float = 0.0
    avg_time: float = 0.0

    def calculate_aggregates(self) -> None:
        ok = [r for r in self.runs if r.success]
        self.total_tokens = sum(r.tokens_total for r in self.runs)
        # стоимость = кодогенерация + агентный сбор контекста (кат. B)
        self.total_cost = sum(r.cost_total for r in self.runs) + self.context_analysis_cost
        self.avg_time = round(sum(r.elapsed_time for r in ok) / len(ok), 3) if ok else 0.0


class ExperimentResult(BaseModel):
    """Эксперимент целиком — то, что пишется в results/experiment_*.json."""

    experiment_name: str
    category: str
    timestamp: str
    models_used: list[str] = Field(default_factory=list)
    tasks_count: int = 0
    runs_per_task: int = 0
    task_results: list[TaskResult] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0
    total_time: float = 0.0

    def calculate_totals(self) -> None:
        self.total_tokens = sum(t.total_tokens for t in self.task_results)
        self.total_cost = sum(t.total_cost for t in self.task_results)
