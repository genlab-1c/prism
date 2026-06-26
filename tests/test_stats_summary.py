"""Тесты сводной статистики (harness/stats/summary): среднее/медиана/σ/95% ДИ + model_stats."""

from __future__ import annotations

import math

import pytest

from harness.stats import summary as ss


def test_mean_median_std():
    assert ss.mean([2, 4, 6]) == 4.0
    assert ss.median([3, 1, 2]) == 2  # нечётное → серединный
    assert ss.median([1, 2, 3, 4]) == 2.5  # чётное → среднее двух
    # несмещённая σ выборки [8,9,10]: var = (1+0+1)/2 = 1 → σ = 1
    assert ss.std([8, 9, 10]) == pytest.approx(1.0)
    assert ss.std([5]) == 0.0  # <2 точек


def test_ci_95_known():
    # [8,9,10]: mean=9, σ=1, n=3, t(df=2)=4.303 → margin = 4.303 * 1/√3 ≈ 2.484
    lo, hi = ss.ci_95([8, 9, 10])
    margin = 4.303 * (1 / math.sqrt(3))
    assert lo == pytest.approx(9 - margin, abs=1e-3)
    assert hi == pytest.approx(9 + margin, abs=1e-3)


def test_ci_95_degenerate():
    assert ss.ci_95([7]) == (7, 7)  # одна точка → интервала нет
    assert ss.ci_95([5, 5, 5]) == (5, 5)  # нулевой разброс → ширина 0


def test_t_crit():
    assert ss._t_crit(2) == 12.706  # df=1
    assert ss._t_crit(3) == 4.303  # df=2
    assert ss._t_crit(50) == 1.96  # df≥30 → нормальное приближение


def _auto(rows: dict[str, dict[str, list[list[float | None]]]]) -> dict:
    """Собрать минимальный auto_l1 из {model: {task: [[S,M,O,P,Q], ...прогоны]}}."""
    tasks = []
    for model, by_task in rows.items():
        for tid, runs in by_task.items():
            tasks.append(
                {
                    "task_id": tid,
                    "model_id": model,
                    "model_name": model.upper(),
                    "runs": [{"scores": dict(zip(ss.AXES, r, strict=True))} for r in runs],
                }
            )
    return {"tasks": tasks}


def test_model_stats_runs1_sorting_and_ci():
    # две модели, две задачи, по одному прогону → ДИ = межзадачный разброс
    auto = _auto(
        {
            "good": {"A1": [[10, 10, 10, None, 10.0]], "A2": [[10, 8, 10, None, 8.0]]},
            "weak": {"A1": [[10, 0, 10, None, 5.0]], "A2": [[10, 2, 10, None, 5.5]]},
        }
    )
    stats = ss.model_stats(auto)
    assert [m.model_id for m in stats] == ["good", "weak"]  # сортировка по Q̄ убыв.
    g = stats[0]
    assert g.q.mean == pytest.approx(9.0)  # (10+8)/2
    assert g.q.n == 2 and g.n_tasks == 2
    assert g.axes["P"].n == 0  # P везде N/A → исключён, выборка пуста
    # ДИ ненулевой (разброс есть)
    assert g.q.ci_hi > g.q.ci_lo


def test_model_stats_averages_runs_within_task():
    # один прогон-пара даёт M 0 и 10 на одной задаче → позадачное значение = 5
    auto = _auto({"m": {"A1": [[10, 0, 10, None, 5.0], [10, 10, 10, None, 10.0]]}})
    stats = ss.model_stats(auto)
    m = stats[0]
    assert m.axes["M"].n == 1  # одна задача
    assert m.axes["M"].mean == pytest.approx(5.0)  # (0+10)/2 внутри задачи
    assert m.axes["Q"].mean == pytest.approx(7.5)  # (5+10)/2


def test_ci_overlap():
    a = ss.AxisStat(mean=8, median=8, std=1, ci_lo=7, ci_hi=9, n=5)
    b = ss.AxisStat(mean=8.5, median=8.5, std=1, ci_lo=8, ci_hi=10, n=5)  # перекрытие
    c = ss.AxisStat(mean=4, median=4, std=1, ci_lo=3, ci_hi=5, n=5)  # без перекрытия с a
    assert ss.ci_overlap(a, b) is True
    assert ss.ci_overlap(a, c) is False
