"""Точка входа пользователя: `prism <команда>`.

Тонкий диспетчер — бизнес-логики тут нет, только разбор аргументов и вызов:
  prism score   — авто-оценка L1 готовых генераций по изданию → results/auto/
  prism check   — целостность: контракты метрики, задания, эталоны, инструменты

Зарегистрирован как консольный скрипт в pyproject ([project.scripts] prism).
Запуск без установки:  python3 -m harness.cli <команда>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness import check, orchestrate

_GLYPH = {"ok": "✓", "warn": "⚠", "fail": "✗", "skip": "·"}


def cmd_score(args: argparse.Namespace) -> int:
    experiment = args.experiment or orchestrate.newest_experiment()
    orchestrate.score_report(experiment, args.edition, args.out)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    sections, ok = check.run_checks()
    for s in sections:
        print(f"\n{s['title']}")
        for status, text in s["items"]:
            print(f"  {_GLYPH.get(status, '?')} {text}")
    fails = sum(st == "fail" for s in sections for st, _ in s["items"])
    warns = sum(st == "warn" for s in sections for st, _ in s["items"])
    print(f"\n{'ОК' if ok else 'ЕСТЬ НАРУШЕНИЯ'}: "
          f"{fails} fail, {warns} warn")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="prism", description="PRISM — бенчмарк кодогенерации 1С.")
    sub = ap.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("score", help="авто-оценка L1 готовых генераций по изданию")
    sc.add_argument("--experiment", type=Path, default=None,
                    help="путь к experiment_*.json (по умолчанию свежайший experiment_A_*)")
    sc.add_argument("--edition", default="core", help="издание из editions/ (по умолчанию core)")
    sc.add_argument("--out", type=Path, default=None,
                    help="куда писать (по умолчанию results/auto/<exp>_auto_l1.json)")
    sc.set_defaults(func=cmd_score)

    ch = sub.add_parser("check", help="проверка целостности контрактов, заданий, эталонов")
    ch.set_defaults(func=cmd_check)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
