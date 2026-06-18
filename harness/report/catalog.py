"""Видимый банк задач: tasks/README.md, собранный ИЗ task.yaml.

Зачем: чтобы контрибьютор одним взглядом видел, что уже в бенчмарке (и не
предлагал дубликат), не открывая десятки сырых каталогов. Файл генерируется,
руками не правится — источник правды остаётся в task.yaml (правило репо: данные
не живут в прозе, проза собирается из данных).

  prism tasks      — пересобрать (или make tasks-index)
  prism check      — гейтит свежесть (банк не должен отставать от task.yaml)
"""

from __future__ import annotations

import re
from pathlib import Path

from harness.loaders import PRISM, Task, load_tasks

# Файл рендерится в корень банка — GitHub показывает его при заходе в tasks/.
REL_PATH = Path("tasks") / "README.md"

_DIFF_RU = {"easy": "🟢 easy", "medium": "🟠 medium", "hard": "🔴 hard"}


def path(root: Path = PRISM) -> Path:
    return root / REL_PATH


def _order(t: Task) -> tuple[str, int, str]:
    """Натуральный порядок: A раньше B, внутри — по числу (A2 раньше A10)."""
    m = re.match(r"([A-Za-z]+)(\d+)", t.id)
    return (t.category, int(m.group(2)) if m else 0, t.id)


def _tags(t: Task, dim: str) -> str:
    return ", ".join(t.tags.get(dim, [])) or "—"


def render(root: Path = PRISM) -> str:
    """Markdown банка задач из текущих task.yaml. Детерминирован (стабильный порядок)."""
    tasks = sorted(load_tasks(root), key=_order)
    a = [t for t in tasks if t.category == "A"]
    b = [t for t in tasks if t.category == "B"]

    out: list[str] = []
    out.append("<!-- СГЕНЕРИРОВАНО `prism tasks` — НЕ ПРАВИТЬ РУКАМИ.")
    out.append("     Источник правды — tasks/category_*/<id>/task.yaml.")
    out.append("     Пересобрать: make tasks-index (свежесть гейтит make check). -->")
    out.append("")
    out.append("# Банк задач PRISM")
    out.append("")
    out.append("Полный список задач, **уже включённых** в бенчмарк. Загляните сюда **перед тем,")
    out.append("как предлагать новую** — дубликаты не нужны, ценно разнообразие (новый паттерн,")
    out.append("а не ещё одна вариация существующего). Как добавить задачу —")
    out.append("[CONTRIBUTING.md](../CONTRIBUTING.md).")
    out.append("")
    out.append(f"Всего **{len(tasks)}**: категория A — {len(a)}, категория B — {len(b)}.")
    out.append("")
    out.append("> _Файл собран из `task.yaml` командой `prism tasks` — не правьте вручную._")
    out.append("")

    out.append(f"## Категория A — алгоритмика на чистом BSL ({len(a)})")
    out.append("")
    out.append("Исполняется в OneScript (без платформы 1С). Ось P неприменима.")
    out.append("")
    out.append("| ID | Задача | Сложность | Навыки |")
    out.append("|----|--------|:---:|--------|")
    for t in a:
        out.append(
            f"| {t.id} | {t.name} | {_DIFF_RU.get(t.difficulty, t.difficulty)} | {_tags(t, 'skill')} |"
        )
    out.append("")

    out.append(f"## Категория B — платформенные задачи ({len(b)})")
    out.append("")
    out.append("Исполняются в реальной 1С против синтетической базы из описания задачи.")
    out.append("Колонка «Объекты» — метаданные, которых задача касается (сид оси Платформа).")
    out.append("")
    out.append("| ID | Задача | Сложность | Навыки | Конструкции 1С | Объекты метаданных |")
    out.append("|----|--------|:---:|--------|--------|--------|")
    for t in b:
        objects = "<br>".join(t.expected_objects) or "—"
        out.append(
            f"| {t.id} | {t.name} | {_DIFF_RU.get(t.difficulty, t.difficulty)} | "
            f"{_tags(t, 'skill')} | {_tags(t, 'platform')} | {objects} |"
        )
    out.append("")
    return "\n".join(out)


def write(root: Path = PRISM) -> Path:
    """Пересобрать банк задач на диск. Возвращает путь."""
    p = path(root)
    p.write_text(render(root), encoding="utf-8")
    return p


def is_current(root: Path = PRISM) -> bool:
    """Совпадает ли файл на диске с тем, что сгенерировалось бы сейчас."""
    p = path(root)
    return p.exists() and p.read_text(encoding="utf-8") == render(root)
