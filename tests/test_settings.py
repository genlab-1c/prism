"""Типизированная загрузка ключей доступа (harness.settings.Credentials)."""

from __future__ import annotations

from harness.settings import Credentials


def test_as_env_maps_set_fields_to_uppercase(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-1")
    env = Credentials(_env_file=None).as_env()  # _env_file=None — без чтения реального .env
    assert env["OPENROUTER_API_KEY"] == "sk-test"
    assert env["YANDEX_FOLDER_ID"] == "folder-1"


def test_absent_keys_excluded_from_env(monkeypatch):
    for var in ("OPENROUTER_API_KEY", "GIGACHAT_AUTH_KEY", "YANDEX_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    env = Credentials(_env_file=None).as_env()
    assert "GIGACHAT_AUTH_KEY" not in env  # None-поля в окружение адаптера не попадают


def test_env_var_overrides_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    # окружение приоритетнее .env
    assert Credentials(_env_file=dotenv).as_env()["OPENROUTER_API_KEY"] == "from-env"
