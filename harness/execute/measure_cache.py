"""Кэш сырых замеров песочницы: не считать то, что не могло измениться.

Зачем. Смена ПРАВИЛ оценки (протокол, пороги, логика скорера) не меняет вход песочницы:
код кандидата тот же, задача та же, инструмент тот же. Значит и вывод движка будет тот же —
он детерминирован (проверено: два прогона дают одинаковые счётчики до последней цифры).
Без кэша полный пересчёт категории A занимает около часа, категории B — часы, и почти всё
это время движок заново получает уже известный ответ.

Ключ — СОДЕРЖИМОЕ входа, а не имя файла. Для прогонов категории A вход это сам текст скрипта:
харнесс собирает его из кода кандидата, скрытых тестов и своей логики сборки, поэтому любое
изменение любой из трёх частей меняет текст, а значит и ключ. Такой ключ самоинвалидируется:
ошибиться в нём, забыв учесть какой-то вход, почти невозможно.

Чего кэш НЕ хранит: баллы. Только сырьё — вывод движка. Балл выводится заново каждый раз,
поэтому правка протокола применяется мгновенно и ко всему корпусу.

Выключается переменной PRISM_NO_CACHE=1 (например, чтобы перепроверить движок на живую).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from harness.loaders import PRISM

CACHE_DIR = PRISM / "results" / ".measure_cache"
VERSION = "1"  # поднять, если поменялся ФОРМАТ записи кэша (не путать с содержимым входа)


def enabled() -> bool:
    return os.environ.get("PRISM_NO_CACHE", "") not in ("1", "true", "yes")


def key(kind: str, *parts: str) -> str:
    """Ключ замера: вид + все входы, которые влияют на сырой результат."""
    h = hashlib.sha256()
    h.update(f"{VERSION}\0{kind}".encode())
    for p in parts:
        h.update(b"\0")
        h.update(p.encode("utf-8", errors="replace"))
    return h.hexdigest()


def get(k: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    path = CACHE_DIR / k[:2] / f"{k}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def put(k: str, value: dict[str, Any]) -> None:
    if not enabled():
        return
    path = CACHE_DIR / k[:2] / f"{k}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # атомарно: параллельные скореры не увидят половину записи
    except OSError:
        pass  # кэш — ускорение, а не источник правды: не смог записать, просто считаем заново


def stats() -> dict[str, int]:
    """Сколько записей в кэше и сколько они занимают (для отчётов и очистки)."""
    files = list(CACHE_DIR.rglob("*.json")) if CACHE_DIR.exists() else []
    return {"записей": len(files), "байт": sum(f.stat().st_size for f in files)}
