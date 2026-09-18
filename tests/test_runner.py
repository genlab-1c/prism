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

requires_local = pytest.mark.skipif(not local.available(), reason="oscript не установлен")
requires_docker = pytest.mark.skipif(
    not in_docker.available(), reason="нет docker-образа prism-onescript"
)


# ── фабрика ──────────────────────────────────────────────────────────────────


def test_factory_default_docker(monkeypatch):
    monkeypatch.delenv("PRISM_RUNNER", raising=False)
    assert get_runner().name == "docker"  # песочница по умолчанию (недоверенный код LLM)


def test_factory_env(monkeypatch):
    monkeypatch.setenv("PRISM_RUNNER", "local")
    assert get_runner().name == "local"


def test_factory_arg_beats_env(monkeypatch):
    monkeypatch.setenv("PRISM_RUNNER", "local")
    assert get_runner("docker").name == "docker"


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
def test_local_endless_loop_burns_the_cpu_budget(tmp_path):
    """Вечный цикл жжёт процессор — это исчерпание бюджета, то есть вина кода.

    Сторож по настенным часам тут не при чём: он срабатывает, когда процесс НЕ считает
    (зависшее окружение), и означает «не измерено».
    """
    script = tmp_path / "loop.os"
    script.write_text("Пока Истина Цикл КонецЦикла;", encoding="utf-8")
    res = local.run_os(script, timeout=2)
    assert res.cpu_exhausted and not res.timed_out


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
        "Попытка\n"
        '    Соединение = Новый HTTPСоединение("example.com",, , , , 3);\n'
        '    Ответ = Соединение.Получить(Новый HTTPЗапрос("/"));\n'
        '    Сообщить("NET_OPEN");\n'
        "Исключение\n"
        '    Сообщить("NET_BLOCKED");\n'
        "КонецПопытки;\n",
        encoding="utf-8",
    )
    res = in_docker.run_os(script, timeout=30)
    assert "NET_BLOCKED" in res.stdout
    assert "NET_OPEN" not in res.stdout


# ── бюджет процессорного времени против сторожа по часам ─────────────────────


def test_cpu_exhausted_is_told_apart_from_a_stalled_machine(tmp_path, monkeypatch):
    """Два разных исхода: кандидат сжёг бюджет (вина кода) и окружение зависло (не измерено).

    Раньше оба выглядели как «таймаут», и балл зависел от того, чем ещё занята машина:
    запись A14 · GPT-5.6 Luna Max дважды теряла балл O под нагрузкой (F18 плана гигиены).
    """
    import subprocess as sp

    from harness.execute.runner import LocalRunner

    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")

    monkeypatch.setattr(
        sp, "run", lambda cmd, **kw: sp.CompletedProcess(cmd, 152, stdout="", stderr="")
    )
    burned = LocalRunner().run_os(script, timeout=3)
    assert burned.cpu_exhausted is True and burned.timed_out is False

    def stall(cmd, **kw):
        raise sp.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(sp, "run", stall)
    stalled = LocalRunner().run_os(script, timeout=7)  # другой бюджет → мимо кэша
    assert stalled.timed_out is True and stalled.cpu_exhausted is False


def test_wall_guard_is_far_above_the_cpu_budget(tmp_path, monkeypatch):
    """Сторож по часам не должен срабатывать раньше бюджета: он против зависаний, не про скорость."""
    import subprocess as sp

    from harness.execute.runner import WALL_FACTOR, LocalRunner

    seen: dict = {}

    def capture(cmd, **kw):
        seen.update(kw)
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", capture)
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    LocalRunner().run_os(script, timeout=11)
    assert seen["timeout"] == 11 * WALL_FACTOR and WALL_FACTOR >= 3
