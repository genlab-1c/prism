"""Единый rich-вывод харнесса: общий Console + статус-глифы для check.

Console сам деградирует на НЕ-tty (пайп, CI, перехват pytest): без управляющих кодов,
обычный текст и без живого прогресс-бара — поэтому машинный вывод и тесты не страдают.
"""

from __future__ import annotations

from rich.console import Console

console = Console()

# статус среза check → (глиф, rich-стиль)
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "ok": ("✓", "green"),
    "warn": ("⚠", "yellow"),
    "fail": ("✗", "bold red"),
    "skip": ("·", "dim"),
}
