#!/usr/bin/env python3
"""Восстановить время генерации старых записей по истории репозитория.

Зачем. Поле ``generated_at`` появилось в волне 0 аудита корпуса, и прогон с тех пор пишет
его сам. Старые записи дозаполнялись по датам файлов-чекпойнтов, а те переписывались при
каждом повторном прогоне, поэтому у 1807 записей из 1820 стояла дата последнего пересчёта:
модель, объявленная в июне, датировалась сентябрём.

Как надёжнее. У каждого ответа есть ``response_hash``. Ответ попал в репозиторий тем
коммитом, который первым принёс этот хеш, и время того коммита и есть верхняя граница
времени генерации: позже ответ появиться не мог, а раньше коммита его в истории нет.
Инструмент проходит коммиты, тронувшие ``results/``, от старых к новым, и для каждого
хеша запоминает первое появление.

Что НЕ трогается: записи, у которых время записал сам прогон (``provenance`` пуст).
Ответы, баллы и хеши не меняются вовсе — правится только метка времени и провенанс,
поэтому пересчёт не требуется.

Запуск:
    python3 tools/backfill_generated_at.py --dry-run   # показать, что изменится
    python3 tools/backfill_generated_at.py             # записать
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "results"
EXP_RE = re.compile(r"^results/experiment_[AB]_\d{8}_\d{6}\.json$")
MARK = "восстановлено по истории репозитория"


def git(*args: str) -> str:
    # S603/S607: аргументы собираются здесь же, из внешнего ввода ничего не приходит,
    # а git берётся из PATH намеренно, как и в остальном инструментарии репозитория.
    out = subprocess.run(  # noqa: S603, S607
        ["git", *args],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout


def commits_touching_results() -> list[tuple[str, str]]:
    """(хеш, ISO-время) коммитов, тронувших results/, от старых к новым."""
    raw = git("log", "--reverse", "--format=%H|%cI", "--", "results/").strip()
    rows = []
    for line in raw.split("\n"):
        if "|" not in line:
            continue
        h, iso = line.split("|", 1)
        rows.append((h, iso[:19]))  # без часового пояса: остальной корпус тоже наивный
    return rows


def experiment_files(rev: str) -> list[str]:
    names = git("ls-tree", "-r", "--name-only", rev, "results/").split("\n")
    return [n for n in names if EXP_RE.match(n.strip())]


def first_seen() -> dict[tuple[str, str, str], str]:
    """(модель, задача, response_hash) → время коммита, впервые принёсшего этот ответ.

    Ключ тройной не для красоты: две модели нередко выдают на задачу байт в байт один и тот
    же код, и хеш у них совпадает. По одному хешу время уехало бы к той, что сгенерировала
    раньше, и GPT-5.6 Sol датировался бы июнем вместо июля.
    """
    seen: dict[tuple[str, str, str], str] = {}
    commits = commits_touching_results()
    for i, (rev, when) in enumerate(commits, 1):
        for name in experiment_files(rev):
            blob = git("show", f"{rev}:{name}")
            if not blob.strip():
                continue
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                continue  # битая промежуточная ревизия — пропускаем, её перекроет следующая
            for tr in data.get("task_results", []):
                for run in tr.get("runs", []):
                    h = run.get("response_hash")
                    if not h:
                        continue
                    key = (tr.get("model_name", ""), tr.get("task_id", ""), h)
                    if key not in seen:
                        seen[key] = when
        print(f"\r  коммитов просмотрено {i}/{len(commits)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="только показать, ничего не писать")
    args = ap.parse_args()

    seen = first_seen()
    print(f"ответов в истории: {len(seen)}")

    total = touched = kept = missed = 0
    for path in sorted(RESULTS.glob("experiment_[AB]_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for tr in data.get("task_results", []):
            for run in tr.get("runs", []):
                total += 1
                if not run.get("provenance"):
                    kept += 1  # время записал сам прогон — источник надёжнее любого вывода
                    continue
                key = (
                    tr.get("model_name", ""),
                    tr.get("task_id", ""),
                    run.get("response_hash") or "",
                )
                when = seen.get(key)
                if not when:
                    missed += 1
                    continue
                if run.get("generated_at") != when or run.get("provenance") != MARK:
                    run["generated_at"] = when
                    run["provenance"] = MARK
                    changed += 1
        touched += changed
        print(f"  {path.name}: обновлено {changed}")
        if changed and not args.dry_run:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"\nзаписей {total} · обновлено {touched} · оставлено как есть {kept}"
        f" · без следа в истории {missed}"
    )
    if args.dry_run:
        print("режим проверки: файлы не изменены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
