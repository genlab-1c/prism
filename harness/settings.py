"""Типизированная загрузка ключей доступа к моделям — окружение + .env.

pydantic-settings подхватывает `.env` из корня репозитория АВТОМАТИЧЕСКИ: ручной
`set -a && source .env && set +a` больше не нужен. Приоритет источников (как у pydantic-
settings): переменные окружения > .env > пусто. Все поля опциональны — нужны лишь ключи
тех адаптеров, что реально гоняются (см. generation/models.yaml → access.adapter); чего
нет, то остаётся None и в окружение адаптера не попадает (понятная ошибка «нет KEY», а не
падение в сети).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env ищем рядом с репозиторием (harness/ → корень), а не от CWD — чтобы подхват
# работал из любого рабочего каталога.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Credentials(BaseSettings):
    """Ключи доступа к каналам генерации (имена полей = переменные окружения, регистронезависимо)."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_api_key: str | None = None
    openai_compat_api_key: str | None = None
    gigachat_auth_key: str | None = None
    gigachat_scope: str | None = None
    yandex_api_key: str | None = None
    yandex_folder_id: str | None = None

    def as_env(self) -> dict[str, str]:
        """Заданные ключи как {ИМЯ_В_ВЕРХНЕМ_РЕГИСТРЕ: значение} — формат, который ждёт build_adapter."""
        return {name.upper(): value for name, value in self.model_dump().items() if value}


@lru_cache(maxsize=1)
def credentials_env() -> dict[str, str]:
    """Ключи доступа из окружения/.env (читается один раз на процесс)."""
    return Credentials().as_env()
