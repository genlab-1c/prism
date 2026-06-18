"""Единый rich-вывод харнесса: общий Console + статус-глифы для check.

Console сам деградирует на НЕ-tty (пайп, CI, перехват pytest): без управляющих кодов,
обычный текст и без живого прогресс-бара — поэтому машинный вывод и тесты не страдают.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

console = Console()

# статус среза check → (глиф, rich-стиль)
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "ok": ("✓", "green"),
    "warn": ("⚠", "yellow"),
    "fail": ("✗", "bold red"),
    "skip": ("·", "dim"),
}


@contextmanager
def progress_bar(description: str, total: int) -> Iterator[Callable[[], None]]:
    """Живой прогресс-бар для долгих параллельных прогонов (score/check эталоны в 1С).

    Возвращает callable advance() — звать на каждый готовый элемент. Только в
    интерактивном терминале; на не-tty (пайп/CI/тесты) — no-op, чтобы не сорить в логи.
    Общий стиль и поведение для всех долгих операций харнесса.
    """
    if total <= 0 or not console.is_terminal:
        yield lambda: None
        return
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(description, total=total)
        yield lambda: progress.advance(task_id)
