"""Точка входа пользователя: `prism <команда>`.

Тонкий диспетчер — бизнес-логики тут нет, только разбор аргументов и вызов:
  prism doctor   — готовность окружения: инструменты осей, ключи моделей (без сети)
  prism ping     — живой минимальный запрос к моделям (проверка ключа/связи)
  prism generate — сгенерировать код кандидатов моделями по изданию → results/
                   (--mock — сухой прогон конвейера без сети)
  prism score    — авто-оценка L1 готовых генераций по изданию → results/auto/
  prism check    — целостность: контракты метрики, задания, эталоны, инструменты
  prism submit   — упаковать прогон для шеринга (хеш совместимости) / принять чужой
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
from harness.ui import ACCENT, brand_title, console, print_logo, print_status_sections

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
    if args.mock:  # сухой прогон конвейера: без сети и ключей (имитация модели mock/echo)
        from harness.generate.mock import build_mock_runner

        brand_title(f"генерация · имитация ({args.mock})")
        console.print("  [dim]без сети и ключей · модель mock/echo[/dim]\n", highlight=False)
        exp = build_mock_runner(args.mock, verbose=True).run_experiment(
            args.category, task_ids=args.tasks, edition_name=args.edition
        )
        console.print(
            f"\n  [green]→ results/{exp.experiment_name}.json[/green]  "
            f"[dim]({exp.tasks_count} задач × 1 модель · имитация)[/dim]",
            highlight=False,
        )
        console.print(
            f"  [dim]дальше:[/dim] prism score --experiment results/{exp.experiment_name}.json",
            highlight=False,
        )
        return 0

    from harness.generate.run import GenerationRunner

    runner = GenerationRunner(
        concurrency=args.concurrency, max_cost=args.max_cost, retries=args.retries, verbose=True
    )

    if args.dry_run:  # предполётная оценка стоимости, без сети
        est = runner.estimate(args.category, model_keys=args.models, task_ids=args.tasks)
        brand_title("генерация · смета стоимости")
        console.print(
            f"  ≈ {est['pairs']} пар · [bold]${est['total']:.4f}[/bold]  "
            f"[dim](грубая верхняя оценка, цены на {est['as_of'] or '—'})[/dim]",
            highlight=False,
        )
        for mid, cost in est["by_model"].items():
            console.print(f"    [dim]{mid}[/dim]  ${cost:.4f}", highlight=False)
        if est["unknown_price"]:
            console.print(
                f"  [yellow]● нет цены (бюджет недосчитан): "
                f"{', '.join(est['unknown_price'])}[/yellow]",
                highlight=False,
            )
        return 0

    brand_title("генерация")
    exp = runner.run_experiment(
        args.category,
        model_keys=args.models,
        task_ids=args.tasks,
        edition_name=args.edition,
        resume=args.resume,
    )
    console.print(
        f"\n  [green]→ results/{exp.experiment_name}.json[/green]  "
        f"[dim]({exp.tasks_count} задач × {len(exp.models_used)} моделей · "
        f"токенов {exp.total_tokens} · ${exp.total_cost:.4f})[/dim]",
        highlight=False,
    )
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    from harness.generate.run import GenerationRunner

    name = args.experiment  # принимаем имя, путь к json или к .parts
    if name.endswith(".parts"):
        name = name[: -len(".parts")]
    elif name.endswith(".json"):
        name = name[: -len(".json")]
    name = Path(name).name  # отрезаем results/ при пути

    exp = GenerationRunner().rebuild_from_parts(name)
    brand_title("пересборка рулона из чекпойнтов")
    console.print(
        f"  [green]→ results/{exp.experiment_name}.json[/green]  "
        f"[dim]({exp.tasks_count} задач × {len(exp.models_used)} моделей · "
        f"пар {len(exp.task_results)} · токенов {exp.total_tokens})[/dim]",
        highlight=False,
    )
    console.print(f"  [dim]модели:[/dim] {', '.join(exp.models_used)}", highlight=False)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    _apply_runtime_flags(args)
    if args.experiment:  # явный набор генераций — считаем именно его
        orchestrate.score_report(
            args.experiment,
            args.edition,
            args.out,
            full=args.full,
            model_keys=args.models,
            task_ids=args.task,
        )
        return 0
    if args.out:  # без --experiment пишем в свой auto_l1 на категорию → один --out неоднозначен
        raise SystemExit("--out требует явного --experiment")
    experiments = orchestrate.newest_experiments()  # свежий прогон КАЖДОЙ категории (A и B)
    if not experiments:
        raise SystemExit("в results/ нет experiment_*.json — сначала `prism generate`")
    for i, (_cat, path) in enumerate(experiments.items()):
        if i:
            console.print()
        orchestrate.score_report(
            path, args.edition, None, full=args.full, model_keys=args.models, task_ids=args.task
        )
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    orchestrate.leaderboard_report(args.experiment, full=args.full)
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    from rich.table import Table

    from harness.loaders import load_tasks
    from harness.report import catalog

    path = catalog.write()
    tasks = load_tasks()
    brand_title("банк задач")
    for cat, title in (("A", "алгоритмика"), ("B", "платформа")):
        rows = sorted((t for t in tasks if t.category == cat), key=lambda t: int(t.id[1:]))
        if not rows:
            continue
        console.print(f"  [dim]категория {cat} · {title} · {len(rows)}[/dim]", highlight=False)
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold", width=4)  # id (для --task / --tasks)
        grid.add_column()  # имя
        grid.add_column(style="dim")  # сложность
        for t in rows:
            grid.add_row(t.id, t.name, t.difficulty or "")
        console.print(grid)
        console.print()
    a = sum(t.category == "A" for t in tasks)
    console.print(
        f"  [dim]→ {path.relative_to(path.parents[1])} пересобран · "
        f"всего {len(tasks)} (A: {a}, B: {len(tasks) - a})[/dim]\n",
        highlight=False,
    )
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    from harness.report import leaderboard_md

    changed = leaderboard_md.write()
    for p in changed:
        console.print(f"→ {p.name} обновлён", style="green", highlight=False)
    console.print("  таблицы лидерборда и счётные бейджи пересобраны из results/auto/", style="dim")
    return 0


def cmd_charts(args: argparse.Namespace) -> int:
    from harness.report import charts

    if not charts.check_matplotlib_available():
        console.print(
            "matplotlib не установлен. Поставьте группу графиков: uv sync --group charts",
            style="red",
        )
        return 1
    made = charts.generate(args.out, top=args.top)
    if not made:
        console.print("нет оценок в results/auto/ — сначала прогоните prism score", style="red")
        return 1
    for p in made:
        console.print(f"→ {p}", style="green", highlight=False)
    console.print(
        f"  {len(made)} файлов (SVG + PNG) — publication-quality графики SMOP", style="dim"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    _apply_runtime_flags(args)
    only = set(args.task) if args.task else None
    sections, ok = check.run_checks(only=only, category=args.category)
    brand_title("проверка целостности")
    print_status_sections(sections)
    fails = sum(st == "fail" for s in sections for st, _ in s["items"])
    warns = sum(st == "warn" for s in sections for st, _ in s["items"])
    warn_tail = f"   [yellow]предупреждений: {warns}[/yellow]" if warns else ""
    if ok:
        console.print(f"  [dim]итог[/dim]   [green]● целостность в порядке[/green]{warn_tail}\n")
    else:
        console.print(f"  [dim]итог[/dim]   [red]● нарушений: {fails}[/red]{warn_tail}\n")
    return 0 if ok else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from harness import preflight

    sections, verdict = preflight.doctor_sections()
    preflight.render_doctor(sections, verdict)
    return 0


def cmd_ping(args: argparse.Namespace) -> int:
    from harness import preflight
    from harness.loaders import load_generation

    catalog = load_generation().models
    unknown = [k for k in (args.models or []) if k not in catalog]
    known = [k for k in (args.models or []) if k in catalog]
    if unknown and not known:  # все запрошенные ключи — мимо каталога: пинговать нечего
        brand_title("связь с моделями")
        console.print(f"  [red]●[/red] нет такой модели: {', '.join(unknown)}", highlight=False)
        console.print("  [dim]список ключей моделей: prism models[/dim]\n", highlight=False)
        return 1
    if unknown:  # часть ключей неизвестна — предупреждаем и пингуем остальные
        console.print(
            f"  [yellow]●[/yellow] пропускаю неизвестные: {', '.join(unknown)} "
            "[dim](prism models)[/dim]",
            highlight=False,
        )
    results = preflight.ping_models(args.models)
    preflight.render_ping(results)
    return 1 if any(r["status"] == "fail" for r in results) else 0


def cmd_models(args: argparse.Namespace) -> int:
    from rich.table import Table

    from harness.generate.adapters.registry import ADAPTER_REQUIRED_KEYS
    from harness.loaders import load_generation
    from harness.settings import credentials_env

    gen = load_generation()
    env = credentials_env()
    brand_title("каталог моделей")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(width=2, justify="center")  # ключ канала есть?
    grid.add_column(style="bold")  # ключ модели (для --models)
    grid.add_column()  # имя
    grid.add_column(style="dim")  # вендор · адаптер
    grid.add_column(style="dim")  # возможности
    has_key = False
    for key, m in gen.models.items():
        caps = m.capabilities or {}
        missing = [k for k in ADAPTER_REQUIRED_KEYS.get(m.access.adapter, []) if k not in env]
        dot = "[green]●[/green]" if not missing else "[dim]○[/dim]"
        has_key = has_key or not missing
        marks = []
        if caps.get("supports_tools"):
            marks.append("tools (кат. B)")
        if caps.get("supports_seed"):
            marks.append("seed")
        grid.add_row(dot, key, m.name, f"{m.vendor} · {m.access.adapter}", " · ".join(marks))
    console.print(grid)
    legend = "  [green]●[/green] ключ канала задан   [dim]○ нет ключа (см. .env.example)[/dim]"
    console.print(f"\n{legend}", highlight=False)
    console.print(
        f"  [dim]всего {len(gen.models)} · пинг: prism ping --models <ключ>[/dim]\n",
        highlight=False,
    )
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    from datetime import datetime

    from harness import submit
    from harness.loaders import PRISM

    if args.verify:  # приём чужого пакета: сверка версии бенчмарка
        brand_title("проверка пакета")
        path = Path(args.verify)
        if not path.exists():  # допускаем короткое имя — ищем в results/submissions/
            alt = PRISM / "results" / "submissions" / path.name
            path = alt if alt.exists() else path
        if not path.exists():
            console.print(f"  [red]●[/red] пакет не найден: {args.verify}", highlight=False)
            subs = sorted((PRISM / "results" / "submissions").glob("*_submission.json"))
            if subs:
                console.print("  [dim]есть в results/submissions/:[/dim]", highlight=False)
                for s in subs:
                    console.print(f"    [dim]{s.name}[/dim]", highlight=False)
            console.print()
            return 1
        info = submit.verify_submission(path)
        sub = info["submission"]
        if not info["compatible"]:
            console.print(
                "  [red]●[/red] несовместимо: прогон на другой версии бенчмарка — цифры несравнимы",
                highlight=False,
            )
            console.print(
                f"  [dim]пакет {str(sub.get('compat_hash', '?'))[:12]} ≠ "
                f"репо {info['current_hash'][:12]}[/dim]\n",
                highlight=False,
            )
            return 1
        console.print(
            "  [green]●[/green] совместимо с текущим репозиторием (compat_hash совпал)",
            highlight=False,
        )
        console.print(f"  [dim]моделей[/dim] {len(sub.get('models', []))}\n", highlight=False)
        if args.apply:
            out = submit.apply_submission(sub)
            console.print(
                f"  [green]→ влито в {out.relative_to(PRISM)}[/green]  "
                f"[dim]пересоберите лидерборд: prism docs[/dim]\n",
                highlight=False,
            )
        else:
            console.print("  [dim]влить в results/auto/: повторите с --apply[/dim]\n")
        return 0

    brand_title("упаковка прогона")
    out, sub = submit.build_submission(args.experiment, created=datetime.now().isoformat())
    console.print(f"  [green]→ {out.relative_to(PRISM)}[/green]", highlight=False)
    console.print(
        f"  [dim]compat_hash[/dim] {sub['compat_hash'][:12]}   "
        f"[dim]моделей[/dim] {len(sub['models'])}",
        highlight=False,
    )
    console.print(
        "  [dim]поделиться: приложите файл к PR или пришлите автору "
        "(он сверит: prism submit --verify)[/dim]\n",
        highlight=False,
    )
    return 0


def print_quickstart() -> None:
    """Шпаргалка-«главная»: что набрать, когда `prism` вызван без команды."""
    print_logo()  # брендовый баннер (тихо ничего на не-tty)
    console.print(
        f"  [dim]GenLab-1C · PRISM[/dim] [bold]v{VERSION}[/bold] [dim]· издание core[/dim]\n",
        highlight=False,
    )
    steps = [
        ("какие задачи в банке", "prism tasks"),
        ("какие модели в каталоге", "prism models"),
        ("всё ли готово к работе", "prism doctor"),
        ("проверить связь с моделями", "prism ping"),
        ("сухой прогон без сети", "prism generate --category A --mock"),
        ("сгенерировать код моделями", "prism generate --category A"),
        ("пересчитать оценку L1", "prism score"),
        ("посмотреть результаты", "prism leaderboard"),
        ("поделиться результатом", "prism submit"),
    ]
    for desc, cmd in steps:
        console.print(f"  {desc:<30}[{ACCENT}]{cmd}[/{ACCENT}]", highlight=False)
    console.print(
        f"\n  справка по любой команде     [{ACCENT}]prism <команда> --help[/{ACCENT}]"
        f"\n  установка и тесты            [{ACCENT}]make setup-all[/{ACCENT}] · "
        f"[{ACCENT}]make test[/{ACCENT}]\n",
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
            "  prism check --task B15       быстро прогнать эталон одной задачи\n\n"
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
            "  prism generate --category A --mock           сухой прогон без сети (эталон)\n"
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
    ge.add_argument(
        "--mock",
        nargs="?",
        const="canonical",
        default=None,
        choices=["canonical", "stub"],
        help="сухой прогон конвейера без сети: имитация модели mock/echo "
        "(canonical — отдаёт эталон задачи, stub — заглушку; по умолчанию canonical)",
    )
    ge.set_defaults(func=cmd_generate)

    lb = sub.add_parser(
        "leaderboard",
        help="мгновенная сводка лидерборда из готовой оценки L1 (без пересчёта)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism leaderboard            свежий лидерборд A и B\n"
            "  prism leaderboard --full     + построчная таблица S·M·O·P·Q и срезы по тегам"
        ),
    )
    lb.add_argument(
        "--experiment",
        type=Path,
        default=None,
        metavar="AUTO_L1",
        help="путь к results/auto/*_auto_l1.json (по умолчанию свежайший каждой категории)",
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
            "  prism score                          свежий прогон A и B → два лидерборда\n"
            "  prism score --full                   + построчные детали S·M·O·P·Q\n"
            "  prism score --models ygpt5_lite ygpt51_pro\n"
            "                                       оценить только эти модели, дозаписать в auto_l1\n"
            "  prism score --task B16 B17 B18 B19 B20\n"
            "                                       оценить только эти задачи на всех моделях\n"
            "  prism score --runner docker          ось M в песочнице Docker"
        ),
    )
    sc.add_argument(
        "--experiment",
        type=Path,
        default=None,
        help="путь к experiment_*.json (по умолчанию свежайший каждой категории — A и B)",
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
        "--task",
        nargs="*",
        default=None,
        metavar="ID",
        help="оценить только эти задачи (напр. --task B16 B17) с дозаписью в auto_l1; "
        "прочие задачи не пересчитываются. Комбинируется с --models",
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

    rb = sub.add_parser(
        "rebuild",
        help="пересобрать experiment_*.json из всех чекпойнтов .parts (без сети)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Зачем: после дозапуска новых моделей через resume рулон-json содержит только\n"
            "пары последнего --models, а .parts хранят полный набор. Команда приводит json\n"
            "к полному составу с диска (источник правды — .parts).\n\n"
            "Пример:\n"
            "  prism rebuild experiment_A_20260617_031633"
        ),
    )
    rb.add_argument("experiment", help="имя эксперимента или путь к experiment_*.json / *.parts")
    rb.set_defaults(func=cmd_rebuild)

    ch = sub.add_parser(
        "check",
        help="проверка целостности контрактов, заданий, эталонов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism check                  полная проверка (гейт перед коммитом)\n"
            "  prism check --task B15       быстро: эталон только задачи B15\n"
            "  prism check --category A     эталоны только категории A"
        ),
    )
    ch.add_argument(
        "--task",
        nargs="*",
        default=None,
        metavar="ID",
        help="экспресс: прогнать эталоны только этих задач (напр. --task B15)",
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
        "tasks", help="показать банк задач (id для --task) и пересобрать tasks/README.md"
    )
    tk.set_defaults(func=cmd_tasks)

    md = sub.add_parser("models", help="показать каталог моделей (ключи для --models, без сети)")
    md.set_defaults(func=cmd_models)

    dc = sub.add_parser(
        "docs",
        help="регенерировать таблицы лидерборда и бейджи в README/leaderboard/status из оценок L1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Подменяет регионы между <!-- prism:KEY --> в README.md, docs/leaderboard.md\n"
            "и docs/status.md данными из results/auto/*_auto_l1.json. Запускать после prism score."
        ),
    )
    dc.set_defaults(func=cmd_docs)

    cg = sub.add_parser(
        "charts",
        help="сгенерировать графики лидерборда (SVG+PNG, matplotlib) из оценок L1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Рендерит ранжир по Q̄, профиль по осям SMOP и радар для топ-N моделей\n"
            "(по A и B) в results/charts/. Нужен matplotlib: uv sync --group charts.\n"
            "Примеры:\n"
            "  prism charts\n"
            "  prism charts --top 6 --out docs/assets/charts"
        ),
    )
    cg.add_argument("--out", default=None, help="каталог вывода (по умолчанию results/charts/)")
    cg.add_argument(
        "--top", type=int, default=8, help="сколько моделей на радаре/сравнении (по умолчанию 8)"
    )
    cg.set_defaults(func=cmd_charts)

    dr = sub.add_parser(
        "doctor",
        help="быстрый чек готовности: окружение, инструменты осей, ключи моделей (без сети)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Не делает прогонов в 1С и сетевых вызовов — только смотрит, что установлено.",
    )
    dr.set_defaults(func=cmd_doctor)

    pg = sub.add_parser(
        "ping",
        help="живой минимальный запрос к моделям — проверить ключ и связь (тратит немного токенов)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Шлёт по одному короткому запросу на модель → расходует немного токенов.\n"
            "Примеры:\n"
            "  prism ping                   все модели каталога с заданными ключами\n"
            "  prism ping --models deepseek gemini"
        ),
    )
    pg.add_argument(
        "--models", nargs="*", default=None, metavar="KEY", help="ключи моделей (по умолчанию все)"
    )
    pg.set_defaults(func=cmd_ping)

    sb = sub.add_parser(
        "submit",
        help="упаковать свой прогон для шеринга (с хеш-суммой совместимости) или принять чужой",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  prism submit                         собрать пакет из свежей оценки L1\n"
            "  prism submit --verify file.json      сверить чужой пакет с этим репо\n"
            "  prism submit --verify file.json --apply   + влить в results/auto/"
        ),
    )
    sb.add_argument(
        "--experiment",
        type=Path,
        default=None,
        metavar="AUTO_L1",
        help="путь к results/auto/*_auto_l1.json для упаковки (по умолчанию свежайший)",
    )
    sb.add_argument(
        "--verify",
        type=Path,
        default=None,
        metavar="FILE",
        help="режим автора: сверить отпечаток пакета с текущим репозиторием",
    )
    sb.add_argument(
        "--apply",
        action="store_true",
        help="с --verify: при совместимости влить оценку в results/auto/",
    )
    sb.set_defaults(func=cmd_submit)

    return ap


def main(argv: list[str] | None = None) -> int:
    from harness.settings import load_runtime_env

    load_runtime_env()  # .env → os.environ (рантайм-переменные PRISM_* работают из .env)
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):  # `prism` без команды → шпаргалка, не ошибка
        print_quickstart()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
