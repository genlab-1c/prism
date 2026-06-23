"""Генератор markdown лидерборда/бейджей (harness/report/leaderboard_md)."""

from __future__ import annotations

import pytest

from harness.report import leaderboard_md as L


def _result(rows: list[tuple[str, dict]]) -> dict:
    """Минимальный auto_l1: одна задача на модель с заданными баллами."""
    return {
        "tasks": [
            {
                "task_id": f"A{i}",
                "model_id": f"id/{name}",
                "model_name": name,
                "runs": [{"scores": s}],
            }
            for i, (name, s) in enumerate(rows)
        ]
    }


def test_overall_ranks_by_q_and_bolds_leader():
    res = _result(
        [
            ("Слабая", {"S": 8, "M": 2, "O": 10, "Q": 6.0}),
            ("Сильная", {"S": 9, "M": 8, "O": 10, "Q": 9.0}),
        ]
    )
    md = L.render_overall(res, "A")
    lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    # первая строка данных (после шапки и разделителя) — лидер по Q, ранг 1
    assert lines[2].startswith("| 1 |") and "**Сильная**" in lines[2]  # лидер: №1, жирный
    assert lines[3].startswith("| 2 |") and "Слабая" in lines[3]  # за ним — №2, слабее
    assert lines[0].startswith("| № | Модель")  # колонка ранга — первой
    assert "| O |" in lines[0] and "| P |" not in lines[0]  # у A есть ось O, нет оси P


def test_overall_includes_p_for_category_b():
    res = _result([("M1", {"S": 9, "M": 1, "O": 9, "P": 4, "Q": 5.0})])
    header = next(ln for ln in L.render_overall(res, "B").splitlines() if "Модель" in ln)
    assert "| № |" in header and "| P |" in header


def test_replace_region_idempotent_and_requires_marker():
    text = "до\n<!-- prism:x -->\nстарое\n<!-- /prism:x -->\nпосле\n"
    once = L._replace_region(text, "x", "новое")
    assert "новое" in once and "старое" not in once
    assert L._replace_region(once, "x", "новое") == once  # повторно — без изменений
    with pytest.raises(SystemExit):
        L._replace_region("нет маркера", "x", "y")
