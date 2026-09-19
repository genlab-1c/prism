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

import gzip
import hashlib
import json
import os
from typing import Any

from harness.loaders import PRISM

CACHE_DIR = PRISM / "results" / ".measure_cache"
# Сырьё, на которое ссылаются опубликованные оценки. Кэш в репозиторий не идёт (десятки
# мегабайт промежуточных замеров), поэтому клонировавший видел балл, но не мог проверить,
# откуда он взялся. Здесь лежит только доказательная часть: прогоны, названные в записях
# (detail.M.run_key). Собирается командой `prism artifacts --export`.
BUNDLE = PRISM / "results" / "artifacts.jsonl.gz"
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


def bundle_get(k: str) -> dict[str, Any] | None:
    """Достать сырьё из выгрузки в репозитории. Для свежего клона это единственный источник.

    Читается построчно и без кэша в памяти: обращение сюда редкое (ручной разбор одной
    записи), а файл лучше не держать целиком ради одного ключа. Сжатие обязательно: логи
    русскоязычные, и в UTF-8 они весят вдвое против числа символов.
    """
    try:
        with gzip.open(BUNDLE, "rt", encoding="utf-8") as fh:
            for line in fh:
                if k not in line:
                    continue  # дешёвый отсев: ключ есть в строке только у своей записи
                row = json.loads(line)
                if row.get("key") == k:
                    return row.get("raw")
    except (OSError, ValueError):
        return None
    return None


def bundle_write(items: dict[str, dict[str, Any]]) -> int:
    """Переписать выгрузку целиком. Ключи сортируются, чтобы дифф был осмысленным."""
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BUNDLE.with_suffix(".tmp")
    # mtime=0 и фиксированное сжатие: у одинакового содержимого выходит байт в байт тот же
    # файл, поэтому пересборка выгрузки не даёт пустого диффа в git.
    body = "".join(
        json.dumps({"key": k, "raw": items[k]}, ensure_ascii=False, sort_keys=True) + "\n"
        for k in sorted(items)
    )
    with (
        open(tmp, "wb") as raw_fh,
        gzip.GzipFile(fileobj=raw_fh, mode="wb", compresslevel=9, mtime=0) as fh,
    ):
        fh.write(body.encode("utf-8"))
    tmp.replace(BUNDLE)
    return len(items)


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
