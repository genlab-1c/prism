"""Тесты слоя исполнения (harness/execute/runner.py): режимы local | docker.

Docker-интеграция (skipif без образа) проверяет и САМУ ПЕСОЧНИЦУ:
тот же скрипт даёт тот же вывод, а сеть изнутри недоступна.
"""

from __future__ import annotations

import pytest

from harness.execute.runner import DockerRunner, LocalRunner, get_runner

HELLO = 'Сообщить("PRISM_OK");\n'

local = LocalRunner()
in_docker = DockerRunner()

requires_local = pytest.mark.skipif(
    not local.available(), reason="oscript не установлен")
requires_docker = pytest.mark.skipif(
    not in_docker.available(), reason="нет docker-образа prism-onescript")


# ── фабрика ──────────────────────────────────────────────────────────────────

def test_factory_default_local(monkeypatch):
    monkeypatch.delenv("PRISM_RUNNER", raising=False)
    assert get_runner().name == "local"


def test_factory_env(monkeypatch):
    monkeypatch.setenv("PRISM_RUNNER", "docker")
    assert get_runner().name == "docker"


def test_factory_arg_beats_env(monkeypatch):
    monkeypatch.setenv("PRISM_RUNNER", "docker")
    assert get_runner("local").name == "local"


def test_factory_unknown_mode():
    with pytest.raises(ValueError):
        get_runner("vm")


# ── local ────────────────────────────────────────────────────────────────────

@requires_local
@pytest.mark.slow
def test_local_runs(tmp_path):
    script = tmp_path / "hello.os"
    script.write_text(HELLO, encoding="utf-8")
    res = local.run_os(script)
    assert res.rc == 0 and "PRISM_OK" in res.stdout and not res.timed_out


@requires_local
@pytest.mark.slow
def test_local_timeout(tmp_path):
    script = tmp_path / "loop.os"
    script.write_text("Пока Истина Цикл КонецЦикла;", encoding="utf-8")
    res = local.run_os(script, timeout=2)
    assert res.timed_out


# ── docker (песочница) ───────────────────────────────────────────────────────

@requires_docker
@pytest.mark.slow
def test_docker_runs_same_as_local(tmp_path):
    script = tmp_path / "hello.os"
    script.write_text(HELLO, encoding="utf-8")
    res = in_docker.run_os(script)
    assert res.rc == 0 and "PRISM_OK" in res.stdout


@requires_docker
@pytest.mark.slow
def test_docker_no_network(tmp_path):
    """Сеть в песочнице отрезана: HTTP-запрос изнутри обязан упасть."""
    script = tmp_path / "net.os"
    script.write_text(
        'Попытка\n'
        '    Соединение = Новый HTTPСоединение("example.com",, , , , 3);\n'
        '    Ответ = Соединение.Получить(Новый HTTPЗапрос("/"));\n'
        '    Сообщить("NET_OPEN");\n'
        'Исключение\n'
        '    Сообщить("NET_BLOCKED");\n'
        'КонецПопытки;\n', encoding="utf-8")
    res = in_docker.run_os(script, timeout=30)
    assert "NET_BLOCKED" in res.stdout
    assert "NET_OPEN" not in res.stdout
