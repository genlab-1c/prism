"""Точка входа пользователя: `prism <команда>`.

Тонкий диспетчер — бизнес-логики тут нет, только разбор аргументов и вызов:
  prism generate — сгенерировать код кандидатов моделями по изданию → results/
  prism score    — авто-оценка L1 готовых генераций по изданию → results/auto/
  prism check    — целостность: контракты метрики, задания, эталоны, инструменты
  prism tasks    — пересобрать видимый банк задач (tasks/README.md) из task.yaml

Зарегистрирован как консольный скрипт в pyproject ([project.scripts] prism).
Запуск без установки:  python3 -m harness.cli <команда>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from harness import check, orchestrate
from harness.ui import STATUS_STYLE, console, print_logo

try:  # версия из метаданных установленного пакета (pyproject [project].version)
    from importlib.metadata import version as _pkg_version

    VERSION = _pkg_version("prism-bench")
except Exception:  # не установлен как пакет (запуск из исходников) — не падаем
    VERSION = "dev"

# Русификация стандартных строк argparse (заголовки справки и тексты ошибок). argparse
# берёт их через модульный gettext-хелпер `_`; подменяем его словарём-переводчиком. Важно
# сделать это ДО создания парсеров — дефолтные группы («команды»/«параметры») и текст -h
# вычисляются в момент конструирования ArgumentParser.
_HELP_RU: dict[str, str] = {
    "usage: ": "использование: ",
    "positional arguments": "команды",
    "options": "параметры",
    "optional arguments": "параметры",
    "show this help message and exit": "показать эту справку и выйти",
    "show program's version number and exit": "показать версию и выйти",
    "the following arguments are required: %s": "не хватает обязательных аргументов: %s",
    "unrecognized arguments: %s": "неизвестные аргументы: %s",
    "argument %s: %s": "аргумент %s: %s",
    "argument %(argument_name)s: %(message)s": "аргумент %(argument_name)s: %(message)s",
    "invalid choice: %(value)r (choose from %(choices)s)": (
        "недопустимое значение %(value)r (допустимо: %(choices)s)"
    ),
    "invalid %(type)s value: %(value)r": "недопустимое значение %(type)s: %(value)r",
    "expected one argument": "ожидался один аргумент",
    "expected at least one argument": "ожидался хотя бы один аргумент",
    "ambiguous option: %(option)s could match %(matches)s": (
        "неоднозначная опция: %(option)s подходит под %(matches)s"
    ),
    "%(prog)s: error: %(message)s\n": "%(prog)s: ошибка: %(message)s\n",
    "unknown parser %(parser_name)r (choices: %(choices)s)": (
        "неизвестная команда %(parser_name)r (доступно: %(choices)s)"
    ),
}
argparse._ = lambda message: _HELP_RU.get(message, message)  # type: ignore[attr-defined]


def _argument_error_ru(self: argparse.ArgumentError) -> str:
    """Русский текст ошибки аргумента: префикс «argument» в ArgumentError.__str__ зашит
    без gettext (Python 3.10), поэтому словарём не ловится — локализуем сам __str__."""
    if self.argument_name is None:
        return str(self.message)
    return f"аргумент {self.argument_name}: {self.message}"


argparse.ArgumentError.__str__ = _argument_error_ru  # type: ignore[method-assign]


def _add_runtime_flags(parser: argparse.ArgumentParser) -> None:
    """Флаги исполнения (дублируют env PRISM_CONCURRENCY/RUNNER/BSL) — общие для score/check."""
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        metavar="N",
        help="параллельных прогонов (поверх env PRISM_CONCURRENCY; по умолчанию ≤4)",
    )
    parser.add_argument(
        "--runner",
        choices=["local", "docker"],
        default=None,
        help="песочница оси M (поверх env PRISM_RUNNER)",
    )
    parser.add_argument(
        "--bsl",
        choices=["local", "docker"],
        default=None,
        help="инструмент осей S/O — BSL LS (поверх env PRISM_BSL)",
    )


def _apply_runtime_flags(args: argparse.Namespace) -> None:
    """CLI-флаги исполнения → переменные окружения (флаг приоритетнее env).

    Параллелизм и выбор песочниц управляются через env (PRISM_CONCURRENCY/RUNNER/BSL);
    флаг просто выставляет соответствующий env, поэтому механизм исполнения остаётся один.
    """
    if getattr(args, "concurrency", None):
        os.environ["PRISM_CONCURRENCY"] = str(args.concurrency)
    if getattr(args, "runner", None):
        os.environ["PRISM_RUNNER"] = args.runner
    if getattr(args, "bsl", None):
        os.environ["PRISM_BSL"] = args.bsl


def cmd_generate(args: argparse.Namespace) -> int:
    from harness.generate.run import GenerationRunner

    runner = GenerationRunner(
        concurrency=args.concurrency, max_cost=args.max_cost, retries=args.retries, verbose=True
    )

    if args.dry_run:  # предполётная оценка стоимости, без сети
        est = runner.estimate(args.category, model_keys=args.models, task_ids=args.tasks)
        print(
            f"≈ {est['pairs']} пар · ${est['total']:.4f} (грубая верхняя оценка, "
            f"цены на {est['as_of'] or '—'})"
        )
        for mid, cost in est["by_model"].items():
            print(f"    {mid}: ${cost:.4f}")
        if est["unknown_price"]:
            print(f"  ⚠ нет цены (бюджет недосчитан): {', '.join(est['unknown_price'])}")
        return 0

    exp = runner.run_experiment(
        args.category,
        model_keys=args.models,
        task_ids=args.tasks,
        edition_name=args.edition,
        resume=args.resume,
    )
    print(
        f"→ results/{exp.experiment_name}.json  "
        f"({exp.tasks_count} задач × {len(exp.models_used)} моделей · "
        f"токенов {exp.total_tokens} · ${exp.total_cost:.4f})"
    )
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    _apply_runtime_flags(args)
    experiment = args.experiment or orchestrate.newest_experiment()
    orchestrate.score_report(
        experiment, args.edition, args.out, full=args.full, model_keys=args.models
    )
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    orchestrate.leaderboard_report(args.experiment, full=args.full)
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    from harness.loaders import load_tasks
    from harness.report import catalog

    path = catalog.write()
    tasks = load_tasks()
    a = sum(t.category == "A" for t in tasks)
    print(
        f"→ {path.relative_to(path.parents[1])}  "
        f"(банк задач пересобран: {len(tasks)} задач — A: {a}, B: {len(tasks) - a})"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    _apply_runtime_flags(args)
    only = set(args.task) if args.task else None
    sections, ok = check.run_checks(only=only, category=args.category)
    for s in sections:
        console.print(f"\n{s['title']}", style="bold", markup=False, highlight=False)
        for status, text in s["items"]:
            glyph, style = STATUS_STYLE.get(status, ("?", "dim"))
            # markup=False — текст среза идёт как есть (возможные «[…]» не трактуются как разметка)
            console.print(f"  {glyph} {text}", style=style, markup=False, highlight=False)
    fails = sum(st == "fail" for s in sections for st, _ in s["items"])
    warns = sum(st == "warn" for s in sections for st, _ in s["items"])
    verdict = "[green]ОК[/green]" if ok else "[bold red]ЕСТЬ НАРУШЕНИЯ[/bold red]"
    console.print(f"\n{verdict}: {fails} fail, {warns} warn", highlight=False)
    return 0 if ok else 1


def print_quickstart() -> None:
    """Шпаргалка-«главная»: что набрать, когда `prism` вызван без команды."""
    print_logo()  # брендовый баннер (тихо ничего на не-tty)
    console.print()
    steps = [
        ("посмотреть результаты", "prism leaderboard"),
        ("пересчитать оценку L1", "prism score"),
        ("проверить целостность", "prism check"),
        ("сгенерировать код моделями", "prism generate --category A"),
    ]
    for desc, cmd in steps:
        console.print(f"  {desc:<30}[cyan]{cmd}[/cyan]", highlight=False)
    console.print(
        "\n  справка по любой команде     [cyan]prism <команда> --help[/cyan]"
        "\n  установка и тесты            [cyan]make setup[/cyan] · [cyan]make test[/cyan]\n",
        highlight=False,
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="prism",
        description="PRISM — бенчмарк кодогенерации 1С.",
        formatter_class=argparse.RawDescriptionHelpFormatter,  # epilog с примерами — как есть
        epilog=(
            "Примеры:\n"
            "  prism                       шпаргалка (эта подсказка)\n"
            "  prism leaderboard           кто впереди (мгновенно, без пересчёта)\n"
            "  prism score --full          пересчитать L1 + построчные детали\n"
            "  prism check --task B17       быстро прогнать эталон одной задачи\n\n"
            "Справка по команде:  prism <команда> --help"
        ),
    )
    ap.add_argument(
        "--version", action="version", version=f"prism {VERSION}", help="показать версию и выйти"
    )
    # без подкоманды — не ошибка, а шпаргалка (см. main); поэтому required=False
    sub = ap.add_subparsers(dest="command", required=False, metavar="<команда>")

    ge = sub.add_parser(
        "generate",
        help="генерация кода кандидатов моделями по изданию",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism generate --category A --dry-run        смета стоимости без сети\n"
            "  prism generate --category A --models deepseek gemini\n"
            "  prism generate --category B --tasks B1 B2 --max-cost 5"
        ),
    )
    ge.add_argument("--category", required=True, choices=["A", "B"], help="категория задач")
    ge.add_argument("--edition", default="core", help="издание из editions/ (по умолчанию core)")
    ge.add_argument("--models", nargs="*", default=None, help="ключи моделей (по умолчанию все)")
    ge.add_argument(
        "--tasks", nargs="*", default=None, help="id задач (по умолчанию все категории)"
    )
    ge.add_argument(
        "--resume",
        default=None,
        metavar="EXP_NAME",
        help="дозапустить эксперимент по имени: пропустить готовые пары",
    )
    ge.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="параллельных пар задача×модель (по умолчанию из params.yaml)",
    )
    ge.add_argument(
        "--max-cost",
        dest="max_cost",
        type=float,
        default=None,
        metavar="USD",
        help="кап стоимости: новые пары не запускать сверх порога",
    )
    ge.add_argument(
        "--retries",
        type=int,
        default=3,
        help="повторов при транзиентном сбое сети (по умолчанию 3)",
    )
    ge.add_argument(
        "--dry-run",
        action="store_true",
        help="только предполётная оценка стоимости, без вызовов сети",
    )
    ge.set_defaults(func=cmd_generate)

    lb = sub.add_parser(
        "leaderboard",
        help="мгновенная сводка лидерборда из готовой оценки L1 (без пересчёта)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism leaderboard            свежайший лидерборд\n"
            "  prism leaderboard --full     + построчная таблица S·M·O·P·Q и срезы по тегам"
        ),
    )
    lb.add_argument(
        "--experiment",
        type=Path,
        default=None,
        metavar="AUTO_L1",
        help="путь к results/auto/*_auto_l1.json (по умолчанию свежайший)",
    )
    lb.add_argument(
        "--full", action="store_true", help="добавить построчную таблицу S·M·O·P·Q и срезы по тегам"
    )
    lb.set_defaults(func=cmd_leaderboard)

    sc = sub.add_parser(
        "score",
        help="авто-оценка L1 готовых генераций по изданию (пересчёт)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism score                          пересчитать свежайший эксперимент → лидерборд\n"
            "  prism score --full                   + построчные детали S·M·O·P·Q\n"
            "  prism score --models ygpt5_lite ygpt51_pro\n"
            "                                       оценить только эти модели, дозаписать в auto_l1\n"
            "  prism score --runner docker          ось M в песочнице Docker"
        ),
    )
    sc.add_argument(
        "--experiment",
        type=Path,
        default=None,
        help="путь к experiment_*.json (по умолчанию свежайший experiment_A_*)",
    )
    sc.add_argument("--edition", default="core", help="издание из editions/ (по умолчанию core)")
    sc.add_argument(
        "--models",
        nargs="*",
        default=None,
        metavar="KEY",
        help="оценить только эти модели (ключи каталога) с дозаписью в существующий auto_l1; "
        "прежние модели не пересчитываются",
    )
    sc.add_argument(
        "--out",
        type=Path,
        default=None,
        help="куда писать (по умолчанию results/auto/<exp>_auto_l1.json)",
    )
    sc.add_argument(
        "--full", action="store_true", help="построчная таблица S·M·O·P·Q и срезы вместо лидерборда"
    )
    _add_runtime_flags(sc)
    sc.set_defaults(func=cmd_score)

    ch = sub.add_parser(
        "check",
        help="проверка целостности контрактов, заданий, эталонов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism check                  полная проверка (гейт перед коммитом)\n"
            "  prism check --task B17       быстро: эталон только задачи B17\n"
            "  prism check --category A     эталоны только категории A"
        ),
    )
    ch.add_argument(
        "--task",
        nargs="*",
        default=None,
        metavar="ID",
        help="экспресс: прогнать эталоны только этих задач (напр. --task B17)",
    )
    ch.add_argument(
        "--category",
        default=None,
        choices=["A", "B"],
        help="экспресс: прогнать эталоны только этой категории",
    )
    _add_runtime_flags(ch)
    ch.set_defaults(func=cmd_check)

    tk = sub.add_parser(
        "tasks", help="пересобрать видимый банк задач (tasks/README.md) из task.yaml"
    )
    tk.set_defaults(func=cmd_tasks)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):  # `prism` без команды → шпаргалка, не ошибка
        print_quickstart()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
