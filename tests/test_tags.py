"""Тест срезов качества по тегам (harness/stats/tags.py).

Главное — корректность агрегации: МАКРО-среднее (равный вес на задачу, а не на прогон),
правильный n, мультизначность (задача с двумя тегами входит в оба среза). Эти числа
публикуются как «где модель сильна/слаба», поэтому агрегация под тестом.
"""
from __future__ import annotations

from pathlib import Path

from harness.loaders import Task
from harness.stats.tags import tag_profile


def _task(tid: str, tags: dict) -> Task:
    return Task(id=tid, name=tid, category="A", difficulty="easy", prompt="p",
                dir=Path("."), tags=tags)


def _group(task_id: str, m_scores: list) -> dict:
    return {"task_id": task_id,
            "runs": [{"scores": {"M": m, "S": 10, "O": 10, "P": None}} for m in m_scores]}


def test_macro_average_equal_weight_per_task():
    """Тег усредняется ПО ЗАДАЧАМ (макро), а внутри задачи — по прогонам.

    A1: прогоны M=[10,6] → задача 8.0; A2: M=[4] → задача 4.0;
    тег «строки» = (8.0+4.0)/2 = 6.0 (а НЕ (10+6+4)/3 — иначе A1 с 2 прогонами давит).
    """
    tasks = {"A1": _task("A1", {"skill": ["строки"]}),
             "A2": _task("A2", {"skill": ["строки"]})}
    prof = tag_profile([_group("A1", [10, 6]), _group("A2", [4])], tasks)
    assert prof["skill"]["строки"]["M"] == 6.0
    assert prof["skill"]["строки"]["n"] == 2


def test_multivalued_task_enters_each_tag():
    """Задача с тегами [строки, числа] честно попадает в оба среза."""
    tasks = {"A1": _task("A1", {"skill": ["строки", "числа"]})}
    prof = tag_profile([_group("A1", [8])], tasks)
    assert prof["skill"]["строки"]["M"] == 8.0
    assert prof["skill"]["числа"]["M"] == 8.0
    assert prof["skill"]["строки"]["n"] == 1


def test_unmeasured_axis_excluded():
    """n считается по опорной оси M; неизмеренная ось (P в категории A) не двигает срез."""
    tasks = {"A1": _task("A1", {"skill": ["даты"]})}
    prof = tag_profile([_group("A1", [10])], tasks)
    assert prof["skill"]["даты"]["P"] is None
    assert prof["skill"]["даты"]["n"] == 1
