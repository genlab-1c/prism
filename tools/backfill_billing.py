"""Дозаполнить прогоны детализацией токенов из выгрузки биллинга канала.

Зачем: до 2026-09-09 харнесс не сохранял reasoning/cached-токены — провайдер их отдавал,
а разбор ответа читал только общие счётчики. Историю можно восстановить: в выгрузке канала
на каждый запрос есть модель, вход и выход, и эта тройка почти всегда уникальна.

Сопоставление приблизительное (нет task_id и времени запроса в рулонах), поэтому
восстановленные значения помечаются backfilled=true — чтобы их не путали с данными,
пришедшими из живого ответа API.

Использование:
    python tools/backfill_billing.py <файл выгрузки.csv> [--apply]
Без --apply только показывает, что будет изменено.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

PRISM = Path(__file__).resolve().parent.parent


def load_billing(path: Path) -> dict[tuple, list[dict]]:
    """(модель, вход, выход) → записи биллинга."""
    idx: dict[tuple, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["Model"], int(row["PromptTokens"]), int(row["CompletionTokens"]))
            idx[key].append(row)
    return idx


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    csv_path = Path(sys.argv[1])
    apply = "--apply" in sys.argv
    billing = load_billing(csv_path)

    catalog = yaml.safe_load((PRISM / "generation/models.yaml").read_text(encoding="utf-8"))[
        "models"
    ]
    key_to_id = {k: m["id"] for k, m in catalog.items()}

    stats = defaultdict(int)
    for parts in sorted(PRISM.glob("results/*.parts")):
        for chunk in sorted(parts.glob("*.json")):
            model_key = chunk.stem.split("__")[-1]
            model_id = key_to_id.get(model_key)
            if not model_id:
                stats["модель не в каталоге"] += 1
                continue
            data = json.loads(chunk.read_text(encoding="utf-8"))
            touched = False
            for run in data.get("runs", []):
                if run.get("tokens_reasoning") or run.get("backfilled"):
                    stats["уже заполнено"] += 1
                    continue
                hits = billing.get(
                    (model_id, run.get("tokens_input", 0), run.get("tokens_output", 0)), []
                )
                if len(hits) != 1:
                    stats["нет однозначного совпадения"] += 1
                    continue
                row = hits[0]
                run["tokens_reasoning"] = int(row["ReasoningTokens"])
                run["tokens_cached"] = int(row["CachedTokens"])
                run["tokens_cache_write"] = int(row["CacheWriteTokens"])
                run["cost_reported"] = float(row["Cost"])
                run["backfilled"] = True  # значение из выгрузки, не из ответа API
                touched = True
                stats["восстановлено"] += 1
            if touched and apply:
                chunk.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Итог:" if apply else "Пробный прогон (без записи). Итог:")
    for name, count in sorted(stats.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>5} — {name}")
    if not apply:
        print("\nЗапись: добавьте --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
