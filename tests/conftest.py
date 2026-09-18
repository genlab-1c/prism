"""Общие предпосылки для всех тестов.

Главная — изоляция кэша замеров. Кэш хранит сырьё прогонов песочницы, и тест с подменённым
`subprocess` записал бы туда выдуманный ответ, который потом подставился бы в НАСТОЯЩИЙ
пересчёт. Поймано на живом примере: тест сохранил «код 152» и следующий тест получил его
вместо своего замера. Поэтому каждый тест работает со своим пустым кэшем.
"""

from __future__ import annotations

import pytest

from harness.execute import measure_cache


@pytest.fixture(autouse=True)
def isolated_measure_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(measure_cache, "CACHE_DIR", tmp_path_factory.mktemp("measure_cache"))
