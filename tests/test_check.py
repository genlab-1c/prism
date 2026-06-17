"""Тесты проверки целостности (harness/check.py) и диспетчера CLI (harness/cli.py).

run_checks на РЕАЛЬНЫХ контрактах репозитория: ни одного fail (skip допустим —
например, когерентность эталонов без OneScript). Это «прехук» целостности данных.
"""

from __future__ import annotations

import pytest

from harness import check, cli

# run_checks/cli check поднимают реальную песочницу (эталоны A в OneScript, B в Docker-1С)
# → медленно. Помечаем модуль slow: `make test-fast` его пропускает, полный `make test` гоняет.
pytestmark = pytest.mark.slow


def test_run_checks_no_failures():
    sections, ok = check.run_checks()
    fails = [(s["title"], text) for s in sections for st, text in s["items"] if st == "fail"]
    assert ok, f"нарушения целостности: {fails}"


def test_run_checks_sections_present():
    sections, _ = check.run_checks()
    titles = {s["title"] for s in sections}
    assert {"Контракты метрики", "Контракты заданий",
            "Когерентность эталонов", "Инструменты по осям"} <= titles


def test_every_item_has_known_status():
    sections, _ = check.run_checks()
    for s in sections:
        for status, _text in s["items"]:
            assert status in {"ok", "warn", "fail", "skip"}, status


def test_cli_check_returns_zero():
    assert cli.main(["check"]) == 0


def test_cli_requires_subcommand(capsys):
    import pytest
    with pytest.raises(SystemExit):
        cli.main([])
