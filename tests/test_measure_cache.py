"""Тесты кэша сырых замеров (harness/execute/measure_cache.py + врезки в раннеры).

Кэш ускоряет пересчёт, но обязан быть НЕВИДИМЫМ для результата: те же входы — тот же ответ,
другие входы — новый замер. Ошибка здесь тиха и опасна (подменит сырьё), поэтому ключ и
границы кэширования закреплены тестами.
"""

from __future__ import annotations

import subprocess

import pytest

from harness.execute import measure_cache as mc
from harness.execute.runner import ExecResult, LocalRunner


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Каталог кэша изолирован общим conftest; здесь только гасим внешнее выключение."""
    monkeypatch.delenv("PRISM_NO_CACHE", raising=False)


# ── ключ ─────────────────────────────────────────────────────────────────────


def test_same_input_same_key():
    assert mc.key("run", "текст", "образ") == mc.key("run", "текст", "образ")


@pytest.mark.parametrize(
    "parts",
    [
        ("run", "другой текст", "образ"),
        ("run", "текст", "другой образ"),
        ("check", "текст", "образ"),
    ],
)
def test_any_input_change_changes_key(parts):
    """Ключ обязан меняться от кода кандидата, версии инструмента и вида замера."""
    assert mc.key(*parts) != mc.key("run", "текст", "образ")


def test_roundtrip_and_miss():
    k = mc.key("run", "текст", "образ")
    assert mc.get(k) is None
    mc.put(k, {"stdout": "ok"})
    assert mc.get(k) == {"stdout": "ok"}


def test_disabled_by_env(monkeypatch):
    """PRISM_NO_CACHE=1 — способ перепроверить движок на живую, минуя сохранённое."""
    k = mc.key("run", "текст", "образ")
    mc.put(k, {"stdout": "ok"})
    monkeypatch.setenv("PRISM_NO_CACHE", "1")
    assert mc.get(k) is None


# ── врезка в раннер ──────────────────────────────────────────────────────────


def _fake_run(calls, stdout="вывод", rc=0):
    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")

    return run


def test_second_identical_run_skips_the_engine(tmp_path, monkeypatch):
    """Тот же скрипт второй раз — движок не зовём, ответ берём сохранённый."""
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    r = LocalRunner()
    first = r.run_os(script)
    second = r.run_os(script)
    assert len(calls) == 1
    assert (first.stdout, first.rc) == (second.stdout, second.rc)


def test_changed_script_is_measured_again(tmp_path, monkeypatch):
    """Код кандидата изменился — старый ответ не подходит, считаем заново."""
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    r = LocalRunner()
    r.run_os(script)
    script.write_text("Функция Другая() КонецФункции", encoding="utf-8")
    r.run_os(script)
    assert len(calls) == 2


def test_timeout_is_not_cached(tmp_path, monkeypatch):
    """Таймаут — свойство загруженной машины, а не входа: сохранять его нельзя."""
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    calls: list = []

    def boom(cmd, **kw):
        calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", boom)
    r = LocalRunner()
    assert r.run_os(script).timed_out is True
    assert r.run_os(script).timed_out is True
    assert len(calls) == 2  # второй раз снова пробуем, а не отдаём «таймаут» из кэша


def test_check_and_run_do_not_share_a_key(tmp_path, monkeypatch):
    """Разбор и исполнение — разные замеры одного файла, путать их нельзя."""
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    r = LocalRunner()
    r.run_os(script)
    r.check_os(script)
    assert len(calls) == 2


def test_codestat_restores_counter_file(tmp_path, monkeypatch):
    """Замер оптимальности отдаёт ещё и файл счётчиков — из кэша он тоже обязан появиться."""
    script = tmp_path / "cand.operf.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    stat = tmp_path / "out" / "cand.operf.json"
    calls: list = []

    def run(cmd, **kw):
        calls.append(cmd)
        stat.parent.mkdir(parents=True, exist_ok=True)
        stat.write_text('{"счётчики": 1}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="PRISM_O_OK", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    r = LocalRunner()
    r.run_os_codestat(script, stat)
    stat.unlink()
    res = r.run_os_codestat(script, stat)
    assert len(calls) == 1
    assert res.stdout == "PRISM_O_OK"
    assert stat.read_text(encoding="utf-8") == '{"счётчики": 1}'


def test_result_is_identical_to_a_live_run(tmp_path, monkeypatch):
    """Кэш невидим для результата: поля ExecResult совпадают с живым прогоном."""
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _fake_run([], stdout="ответ движка", rc=3))
    r = LocalRunner()
    live = r.run_os(script)
    from_cache = r.run_os(script)
    assert from_cache == ExecResult(stdout="ответ движка", stderr="", rc=3, timed_out=False)
    assert live == from_cache


# ── нагрузочный замер кат. B (самый дорогой прогон) ──────────────────────────


def test_perf_key_covers_everything_that_changes_the_measurement(tmp_path):
    """Размер базы, код кандидата и профиль нагрузки обязаны входить в ключ.

    Замер поднимает базу растущего размера и пишет техжурнал — дороже всех прочих.
    Путаница ключей тут означала бы, что счётчики одной задачи приписаны другой.
    """
    from harness.execute.onec.perf_run import _perf_key

    d = tmp_path / "task"
    d.mkdir()
    (d / "config_spec.yaml").write_text("catalogs: {}", encoding="utf-8")
    base = _perf_key("Функция Ф() КонецФункции", d, {"sizes": [20, 80]}, 20, "Ф")
    assert base
    assert base != _perf_key("Функция Ф() КонецФункции", d, {"sizes": [20, 80]}, 80, "Ф")
    assert base != _perf_key("Функция Ф() Возврат 1; КонецФункции", d, {"sizes": [20, 80]}, 20, "Ф")
    assert base != _perf_key("Функция Ф() КонецФункции", d, {"sizes": [20, 99]}, 20, "Ф")
    (d / "config_spec.yaml").write_text("catalogs: {Номенклатура: {}}", encoding="utf-8")
    assert base != _perf_key("Функция Ф() КонецФункции", d, {"sizes": [20, 80]}, 20, "Ф")


def test_perf_result_survives_the_round_trip():
    """Из кэша обязан вернуться тот же результат, а не обеднённый."""
    from harness.execute.onec.perf_run import DbOpsResult

    r = DbOpsResult(size=80, ok=True, cand_sdbl=62, cand_reg_reads=62, cand_rows=140)
    assert DbOpsResult(**r.model_dump()) == r


def test_cpu_budget_is_part_of_the_key(tmp_path, monkeypatch):
    """Тот же скрипт при другом бюджете — другой исход, значит и ключ другой.

    Пойман на живом прогоне: кэш вернул результат вчерашнего лимита, и «исчерпал бюджет»
    выглядело как «уложился». Бюджет обязан входить в ключ.
    """
    script = tmp_path / "cand.os"
    script.write_text("Функция Ф() КонецФункции", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls))
    r = LocalRunner()
    r.run_os(script, timeout=3)
    r.run_os(script, timeout=60)
    assert len(calls) == 2
