"""Единый rich-вывод харнесса: общий Console + статус-глифы для check.

Console сам деградирует на НЕ-tty (пайп, CI, перехват pytest): без управляющих кодов,
обычный текст и без живого прогресс-бара — поэтому машинный вывод и тесты не страдают.
"""

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.console import Console, Group
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

console = Console()

# статус среза check → (глиф, rich-стиль)
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "ok": ("✓", "green"),
    "warn": ("⚠", "yellow"),
    "fail": ("✗", "bold red"),
    "skip": ("·", "dim"),
}

# Пасхалка PRISM_FUN=1: вместо строгого спиннера у прогресс-бара по строке бегает котик.
# Кадры — туда-обратно, чистый ASCII (фиксированная ширина → без дрожания); регистрируем
# в наборе спиннеров rich. Приватный модуль мог измениться — тогда тихо остаёмся на «dots».
_CAT = "prism_cat"
_CAT_TRACK = ["{c}{r}".format(c=" " * i + "=^.^=", r=" " * (8 - i)) for i in range(9)]
try:
    from rich._spinners import SPINNERS

    SPINNERS.setdefault(_CAT, {"interval": 110, "frames": _CAT_TRACK + _CAT_TRACK[-2:0:-1]})
    _HAS_CAT = True
except Exception:
    _HAS_CAT = False


def _spinner_name() -> str:
    """Имя спиннера: котик при PRISM_FUN=1, иначе аккуратные точки."""
    return _CAT if (_HAS_CAT and os.environ.get("PRISM_FUN")) else "dots"


def progress_columns() -> tuple[ProgressColumn, ...]:
    """Колонки прогресс-бара (спиннер · описание · полоса · N/M · время) — единые везде."""
    return (
        SpinnerColumn(spinner_name=_spinner_name()),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )


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
    with Progress(*progress_columns(), console=console) as progress:
        task_id = progress.add_task(description, total=total)
        yield lambda: progress.advance(task_id)


# ── брендовый баннер PRISM ────────────────────────────────────────────────────
# Метафора логотипа (см. assets/brand): белый свет проходит сквозь призму и
# расщепляется в спектр осей S·M·O·P. В баннере слово PRISM залито спектральным
# градиентом тех же 4 цветов; в терминале по слову слева направо пробегает световая
# волна (белый фронт), оставляя за собой расщеплённый спектр — дисперсия.
_LOGO_W = "#E8EDF4"  # белый фронт волны
_LOGO_DIM = "#5B6B7E"  # подпись / ещё не пройденные колонки
_ONEC = "#F4B400"  # «1С» — янтарный акцент бренда
# 4 цветовые стопы спектра S·M·O·P (rgb) — те же hex, что в SVG-логотипе
_SPECTRUM: tuple[tuple[int, int, int], ...] = (
    (124, 126, 248),  # S #7C7EF8
    (34, 211, 238),  # M #22D3EE
    (52, 211, 153),  # O #34D399
    (251, 191, 36),  # P #FBBF24
)
# 5-строчный блочный шрифт; каждая «точка» рисуется как ██ (пропорции терминала)
_FONT: dict[str, tuple[str, ...]] = {
    "P": ("█████", "█   █", "█████", "█    ", "█    "),
    "R": ("█████", "█   █", "█████", "█  █ ", "█   █"),
    "I": ("█████", "  █  ", "  █  ", "  █  ", "█████"),
    "S": ("█████", "█    ", "█████", "    █", "█████"),
    "M": ("█   █", "██ ██", "█ █ █", "█   █", "█   █"),
}
_LOGO_EDGE = 2  # ширина белого фронта световой волны


def _grad_hex(t: float) -> str:
    """Цвет спектрального градиента в точке t∈[0,1] — линейно между 4 стопами S·M·O·P."""
    t = min(1.0, max(0.0, t))
    seg = t * (len(_SPECTRUM) - 1)
    i = min(int(seg), len(_SPECTRUM) - 2)
    f = seg - i
    lo, hi = _SPECTRUM[i], _SPECTRUM[i + 1]
    r, g, b = (round(lo[k] + (hi[k] - lo[k]) * f) for k in range(3))
    return f"#{r:02X}{g:02X}{b:02X}"


def _word_grid(word: str = "PRISM", gap: int = 1) -> list[str]:
    """Слово в блочном шрифте: 5 строк, буквы через gap пробелов."""
    rows = ["" for _ in range(5)]
    for ch in word:
        glyph = _FONT[ch]
        for r in range(5):
            rows[r] += glyph[r] + " " * gap
    return [r.rstrip() for r in rows]


_GRID = _word_grid()
_GRID_W = max(len(r) for r in _GRID)


def _logo_lines(sweep: int | None = None) -> list[Text]:
    """5 строк слова PRISM в спектральном градиенте. sweep — позиция фронта световой
    волны (кадр анимации): колонки правее фронта погашены, на фронте белая вспышка,
    левее — уже расщеплённый спектр. sweep=None — финальный кадр (полный спектр)."""
    out: list[Text] = []
    for row in _GRID:
        line = Text("  ")
        for x, ch in enumerate(row):
            if ch == " ":
                line.append("  ")
                continue
            if sweep is None or x < sweep - _LOGO_EDGE:
                style = _grad_hex(x / max(1, _GRID_W - 1))
            elif x <= sweep:
                style = _LOGO_W  # фронт волны
            else:
                style = _LOGO_DIM  # ещё не пройдено
            line.append("██", style=style)
        out.append(line)
    return out


def _logo_wordmark() -> Text:
    t = Text("  многомерная оценка генерации кода ", style=_LOGO_DIM)
    t.append("1С", style=f"bold {_ONEC}")
    if os.environ.get("PRISM_FUN"):  # пасхалка: котик «подаёт» свет в призму
        t.append("   =^.^=", style=_LOGO_DIM)
    return t


def print_logo() -> None:
    """Брендовый баннер PRISM для «главной» (prism без команды).

    Только в интерактивном терминале; на не-tty (пайп/CI/тесты) — тихо ничего, чтобы
    не сорить управляющими кодами в логи. В терминале по слову пробегает световая
    волна, расщепляясь в спектр S·M·O·P. PRISM_NO_ANIM=1 — сразу финальный кадр.
    """
    if not console.is_terminal:
        return
    console.print()
    if os.environ.get("PRISM_NO_ANIM"):
        for line in _logo_lines():
            console.print(line)
    else:
        from rich.live import Live

        with Live(console=console, refresh_per_second=60) as live:
            # фронт идёт за правый край (+EDGE) — последний кадр выходит полным спектром
            for sweep in range(_GRID_W + _LOGO_EDGE + 1):
                live.update(Group(*_logo_lines(sweep)))
                time.sleep(0.03)
    console.print()
    console.print(_logo_wordmark())
