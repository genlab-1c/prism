"""Сводная статистика по авто-оценке L1: среднее, медиана, σ и 95% доверительный интервал.

Зачем: один балл Q на модель — точечная оценка без меры неопределённости. Здесь считается
разброс ПО ЗАДАЧАМ (а при runs>1 — и по прогонам внутри задачи), чтобы показать на лидерборде
доверительный интервал и честно помечать модели, **неразличимые в пределах шума**.

ДИ — t-распределение для малых выборок (df = n−1), нормальное приближение (z=1.96) при df≥30.
Единица анализа — ЗАДАЧА: внутри задачи прогоны усредняются (как и Q̄ лидерборда), статистика
считается по задачам. Чистый python (`math`) — без numpy/scipy, чтобы статистика жила в лёгком
ядре харнесса (графики, которым нужен matplotlib, — отдельный extra).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

# Оси SMOP + сводный Q (порядок как в лидерборде).
AXES: tuple[str, ...] = ("S", "M", "O", "P", "Q")

# Критические значения t для двустороннего 95% ДИ по степеням свободы df=n−1.
# df≥30 — нормальное приближение z=1.96 (расхождение с t уже <5%).
_T95: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
}


def _t_crit(n: int) -> float:
    """t-критическое для 95% ДИ выборки размера n (df=n−1)."""
    df = n - 1
    if df < 1:
        return 0.0
    return _T95.get(df, 1.96)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


def std(values: list[float], m: float | None = None) -> float:
    """Стандартное отклонение, несмещённая оценка (делитель n−1). <2 точек → 0."""
    if len(values) < 2:
        return 0.0
    m = mean(values) if m is None else m
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(var)


def ci_95(values: list[float]) -> tuple[float, float]:
    """95% ДИ для среднего: (низ, верх). <2 точек → (среднее, среднее) — интервала нет."""
    n = len(values)
    if n < 2:
        m = mean(values)
        return (m, m)
    m = mean(values)
    margin = _t_crit(n) * (std(values, m) / math.sqrt(n))
    return (m - margin, m + margin)


@dataclass(frozen=True)
class AxisStat:
    """Статистика одной оси для модели: среднее ± ДИ по задачам."""

    mean: float
    median: float
    std: float
    ci_lo: float
    ci_hi: float
    n: int  # число задач, по которым ось измерена (N/A исключены)

    @property
    def margin(self) -> float:
        """Полуширина 95% ДИ (то самое «±»)."""
        return (self.ci_hi - self.ci_lo) / 2


@dataclass(frozen=True)
class ModelStat:
    """Сводная статистика модели по всем осям."""

    model_id: str
    model_name: str
    n_tasks: int
    axes: dict[str, AxisStat]

    @property
    def q(self) -> AxisStat:
        return self.axes["Q"]


def axis_stat(task_values: list[float]) -> AxisStat:
    """Статистика оси по списку ПОЗАДАЧНЫХ значений (одно число на задачу)."""
    return AxisStat(
        mean=mean(task_values),
        median=median(task_values),
        std=std(task_values),
        ci_lo=ci_95(task_values)[0],
        ci_hi=ci_95(task_values)[1],
        n=len(task_values),
    )


def model_stats(auto: dict) -> list[ModelStat]:
    """Свести статистику по моделям из auto_l1.

    Для каждой (модель, задача, ось): усредняем прогоны (N/A исключаем); полученное
    позадачное значение идёт в выборку оси. Статистика (среднее, σ, 95% ДИ) считается по
    задачам. Сортировка — по убыванию Q̄. Работает и при runs=1 (тогда выборка = по одному
    значению на задачу → ДИ показывает межзадачный разброс)."""
    per_model: dict[str, dict[str, list[float]]] = defaultdict(lambda: {ax: [] for ax in AXES})
    ids: dict[str, str] = {}
    tasks_seen: dict[str, set] = defaultdict(set)

    # Ключ агрегации — ИМЯ модели, а НЕ model_id: id одной модели может разойтись при смене
    # канала доступа (миграция OpenRouter↔AITUNNEL, разные слаги одного веса). Группировка по id
    # тогда бьёт статистику модели на осколки (например, A10 под новым id → n=1 → ДИ=0), а имя —
    # стабильный ключ, по нему же собирает витрину build-data.
    for t in auto.get("tasks", []):
        name = t.get("model_name", "") or t.get("model_id", "")
        ids.setdefault(name, t.get("model_id", name))
        tasks_seen[name].add(t.get("task_id"))
        runs = t.get("runs", [])
        for ax in AXES:
            vals = [r["scores"][ax] for r in runs if r.get("scores", {}).get(ax) is not None]
            if vals:  # ось измерена хотя бы в одном прогоне этой задачи
                per_model[name][ax].append(mean([float(v) for v in vals]))

    out = [
        ModelStat(
            model_id=ids.get(name, name),
            model_name=name,
            n_tasks=len(tasks_seen[name]),
            axes={ax: axis_stat(per_model[name][ax]) for ax in AXES},
        )
        for name in per_model
    ]
    out.sort(key=lambda m: -m.q.mean)
    return out


def ci_overlap(a: AxisStat, b: AxisStat) -> bool:
    """Перекрываются ли 95% ДИ двух осей → различие «в пределах шума» (неразличимы)."""
    return not (a.ci_hi < b.ci_lo or b.ci_hi < a.ci_lo)
