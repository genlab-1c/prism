"""Дозаполнить прогоны условиями генерации (потолок выхода и время ответа).

Зачем: до 2026-09-11 харнесс не сохранял, с каким `max_tokens` уходил запрос. А дефолт
в generation/params.yaml менялся: 4096 (19834a4, 2026-06-12) → 16384 (9f9a8f3, 2026-06-27)
→ 32768 (9159a3f, 2026-08-14) → 65536 (eb06113, 2026-08-28). Под потолком 4096 reasoning-
модели отдавали пустой ответ, и без этого поля условие прогона восстанавливается только по
датам файлов. Значит условие надо перенести из файловой системы в данные.

Источник даты — время записи чекпойнта пары (results/experiment_*.parts/<TASK>__<model>.json),
зафиксированное в снимке results/auto/snapshots/*/parts_dates.json. Снимок нужен потому, что
сама запись в чекпойнт затирает mtime; после записи время файла восстанавливается.

Что заполняется:
  max_tokens    — потолок эпохи по дате, либо переопределение модели из params.yaml
  generated_at  — время записи чекпойнта (≈ момент ответа модели)
  provenance    — «восстановлено», чтобы не путать с условиями живого прогона

Что НЕ заполняется: reasoning_effort. Исторического значения у нас нет, а нынешний каталог
мог измениться — поле остаётся пустым, то есть «неизвестно».

Самопроверка перед записью: ни один прогон не должен иметь tokens_output больше
предполагаемого потолка. Если есть — карта эпох неверна, инструмент не пишет ничего.

Использование:
    python tools/backfill_provenance.py [--apply]
Без --apply только показывает, что изменится. После --apply пересобрать рулоны:
    prism rebuild experiment_A_20260617_031633 && prism rebuild experiment_B_20260617_031637
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import yaml

PRISM = Path(__file__).resolve().parent.parent

# Потолок выхода по датам: (действует с даты, значение). Границы подтверждены коммитами
# params.yaml; день 2026-06-27 подтверждён эмпирически — в тот день 11 прогонов выдали
# больше 4096 токенов (до 8235), значит новый потолок уже действовал.
EPOCHS = [("2026-06-12", 4096), ("2026-06-27", 16384), ("2026-08-14", 32768), ("2026-08-28", 65536)]
MARK = "восстановлено"


def cap_for(date: str) -> int:
    cap = EPOCHS[0][1]
    for since, value in EPOCHS:
        if date >= since:
            cap = value
    return cap


def overrides() -> dict[str, int]:
    """Переопределения потолка на модель из generation/params.yaml."""
    params = yaml.safe_load((PRISM / "generation/params.yaml").read_text(encoding="utf-8"))
    mp = (params.get("defaults") or {}).get("model_params") or {}
    return {
        k: v["max_tokens"] for k, v in mp.items() if isinstance(v, dict) and v.get("max_tokens")
    }


def load_dates() -> dict[str, dict]:
    snaps = sorted((PRISM / "results/auto/snapshots").glob("*/parts_dates.json"))
    if not snaps:
        print("нет снимка дат чекпойнтов (results/auto/snapshots/*/parts_dates.json)")
        sys.exit(2)
    return json.loads(snaps[-1].read_text(encoding="utf-8"))


def main() -> int:
    apply = "--apply" in sys.argv
    dates, over = load_dates(), overrides()
    planned: list[tuple[Path, dict, float]] = []
    per_cap: Counter = Counter()
    skipped = violations = 0

    for partdir in sorted((PRISM / "results").glob("experiment_*.parts")):
        category = partdir.name.split("_")[1]
        for chunk in sorted(partdir.glob("*.json")):
            task, _, key = chunk.stem.partition("__")
            stamp = dates.get(f"{category}|{task}|{key}")
            if stamp is None:
                print(f"  нет даты для {category} {task} {key} — пропуск")
                skipped += 1
                continue
            when = stamp["date"]
            cap = over.get(key) or cap_for(when[:10])
            data = json.loads(chunk.read_text(encoding="utf-8"))
            touched = False
            for run in data.get("runs", []):
                if run.get("generated_at"):  # уже заполнено — идемпотентность
                    continue
                if run.get("tokens_output", 0) > cap:
                    print(f"  ВЫХОД ВЫШЕ ПОТОЛКА: {task} {key} {run['tokens_output']} > {cap}")
                    violations += 1
                run["max_tokens"] = cap
                run["generated_at"] = when
                run["provenance"] = MARK
                touched = True
                per_cap[cap] += 1
            if touched:
                planned.append((chunk, data, os.stat(chunk).st_mtime))

    print(
        f"\nфайлов к правке: {len(planned)}, прогонов: {sum(per_cap.values())}, пропущено: {skipped}"
    )
    for cap, n in sorted(per_cap.items()):
        print(f"  потолок {cap}: {n} прогонов")
    if violations:
        print(
            f"\nОТМЕНА: {violations} прогонов выдали больше предполагаемого потолка — карта эпох неверна"
        )
        return 1
    if not apply:
        print("\nПробный прогон (без записи). Запись: добавьте --apply")
        return 0
    for chunk, data, mtime in planned:
        chunk.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.utime(chunk, (mtime, mtime))  # время файла — улика даты, возвращаем как было
    print(f"\nзаписано: {len(planned)} чекпойнтов (время файлов сохранено)")
    print("пересоберите рулоны: prism rebuild <имя эксперимента>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
