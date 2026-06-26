"""Генерация markdown лидерборда и счётных бейджей в документации.

Таблицы лидерборда и числа в бейджах — ПРОИЗВОДНЫЕ данные: их источник правды —
results/auto/*_auto_l1.json (оценки L1) + банк задач. Держать их руками = рассинхрон,
поэтому регенерируем командой `prism docs` (см. cli). Команда подменяет помеченные
регионы между `<!-- prism:KEY -->` и `<!-- /prism:KEY -->` в README.md, docs/leaderboard.md
и docs/status.md (lb:*-регионы общие у README и страницы лидерборда сайта).

Регионы:
  badges        — счётные бейджи (задач / тест-кейсов / генераций / моделей);
  lb:a-overall  — таблица кат. A (S·M·O·Q), ранжир по Q̄;
  lb:b-overall  — таблица кат. B (S·M·O·P·Q);
  lb:a-skill    — срез M̄ по навыкам (dimension skill);
  lb:b-platform — срез P̄ по конструкциям 1С (dimension platform);
  status:lb     — компактная сводка Q̄ A/B для docs/status.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean

import yaml

from harness.loaders import PRISM, load_tasks

AUTO = PRISM / "results" / "auto"

# короткие подписи столбцов для среза platform (skill-теги короткие — как есть)
_TAG_LABELS = {
    "виртуальная-таблица": "вирт. таблица",
    "регистр-накопления": "регистр накопл.",
    "регистр-сведений": "регистр свед.",
    "срез-последних": "срез последних",
    "табличная-часть": "таб. часть",
    "документ-движения": "движения",
    "иерархия": "иерархия",
}
_MIN_TASKS_PER_TAG = 3  # тег на 1–2 задачах — шум, в срез не выносим (см. stats/tags)


# ── чтение оценок ─────────────────────────────────────────────────────────────


def _newest_auto(category: str) -> Path | None:
    """Свежайший по mtime auto_l1 категории (experiment_<cat>_*_auto_l1.json)."""
    runs = list(AUTO.glob(f"experiment_{category}_*_auto_l1.json"))
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def _load(category: str) -> dict | None:
    path = _newest_auto(category)
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _ranked(result: dict) -> list[tuple[str, dict, int]]:
    """[(model_name, {axis: среднее|None}, n)] — ранжир по Q̄ убыв. (как print_leaderboard)."""
    axes = ("S", "M", "O", "P", "Q")
    by: dict[str, dict[str, list[float]]] = {}
    for t in result["tasks"]:
        for r in t["runs"]:
            s = r["scores"]
            if s.get("Q") is None:
                continue
            bucket = by.setdefault(t["model_name"], {a: [] for a in axes})
            for a in axes:
                if s.get(a) is not None:
                    bucket[a].append(s[a])
    rows = [
        (name, {a: (mean(v) if v else None) for a, v in b.items()}, len(b["Q"]))
        for name, b in by.items()
    ]
    rows.sort(key=lambda r: r[1]["Q"] if r[1]["Q"] is not None else -1.0, reverse=True)
    return rows


# ── рендер таблиц ──────────────────────────────────────────────────────────────


def _fmt(v: float | None, prec: int = 1) -> str:
    return "—" if v is None else f"{v:.{prec}f}"


def _cell(v: float | None, is_max: bool, prec: int) -> str:
    txt = _fmt(v, prec)
    return f"**{txt}**" if (is_max and v is not None) else txt


def _wrap(table: str) -> str:
    """Центрируем таблицу. Атрибут `markdown` — чтобы Python-Markdown (MkDocs, расширение
    md_in_html) рендерил таблицу внутри <div>; на GitHub атрибут игнорируется."""
    return f'<div align="center" markdown>\n\n{table}\n\n</div>'


def render_overall(result: dict, category: str) -> str:
    rows = _ranked(result)
    axes = ["S", "M", "O"] + (["P"] if category == "B" else []) + ["Q"]
    # Постфиксы O-исп/O-авто убраны — в таблице просто «O»; как именно меряется ось O
    # в каждой категории, объясняет проза страницы лидерборда.
    titles = {"S": "S", "M": "M", "O": "O", "P": "P", "Q": "Q · общий"}
    bold_axes = (
        {"M", "O", "P", "Q"} if category == "A" else {"M", "P", "Q"}
    )  # в A ось O теперь различает — выделяем
    maxes = {a: max((m[a] for _, m, _ in rows if m[a] is not None), default=None) for a in axes}
    head = "| № | Модель | " + " | ".join(titles[a] for a in axes) + " |"
    sep = "|:---:|--------|" + ":---:|" * len(axes)
    out = [head, sep]
    for i, (name, m, _n) in enumerate(rows):
        cells = []
        for a in axes:
            prec = 2 if a == "Q" else 1
            is_max = a in bold_axes and m[a] is not None and abs(m[a] - (maxes[a] or -9)) < 1e-9
            cells.append(_cell(m[a], is_max, prec))
        nm = f"**{name}**" if i == 0 else name
        out.append(f"| {i + 1} | {nm} | " + " | ".join(cells) + " |")
    return _wrap("\n".join(out))


def _dimension_tags(dimension: str) -> list[str]:
    """Порядок тегов измерения из tasks/tags.yaml."""
    doc = yaml.safe_load((PRISM / "tasks" / "tags.yaml").read_text(encoding="utf-8"))
    return list(doc["dimensions"][dimension]["values"])


def render_by_tag(result: dict, dimension: str, axis: str) -> str:
    """Матрица модель × тег: среднее axis по тегам измерения (макро-среднее по задачам).

    Столбцы — теги измерения с n≥3 хотя бы у одной модели (порядок словаря). Строки —
    модели в порядке лидерборда. Жирным — максимум столбца.
    """
    from harness.stats.tags import tag_profile

    tasks_by_id = {t.id: t for t in load_tasks()}
    groups_by_model: dict[str, list] = {}
    for t in result["tasks"]:
        groups_by_model.setdefault(t["model_name"], []).append(t)
    profiles = {
        name: tag_profile(groups, tasks_by_id).get(dimension, {})
        for name, groups in groups_by_model.items()
    }
    order = [name for name, _, _ in _ranked(result)]

    cols = [
        tag
        for tag in _dimension_tags(dimension)
        if max((profiles[m].get(tag, {}).get("n", 0) for m in order), default=0)
        >= _MIN_TASKS_PER_TAG
    ]
    if not cols:
        return _wrap("| Модель |\n|--------|\n| — нет тегов с достаточным n — |")

    def val(name: str, tag: str) -> float | None:
        return profiles[name].get(tag, {}).get(axis)

    maxes = {
        tag: max((val(m, tag) for m in order if val(m, tag) is not None), default=None)
        for tag in cols
    }
    labels = [_TAG_LABELS.get(tag, tag) for tag in cols]
    head = "| Модель | " + " | ".join(labels) + " |"
    sep = "|--------|" + ":---:|" * len(cols)
    out = [head, sep]
    for i, name in enumerate(order):
        cells = [
            _cell(
                val(name, tag),
                val(name, tag) is not None
                and abs((val(name, tag) or -9) - (maxes[tag] or -9)) < 1e-9,
                1,
            )
            for tag in cols
        ]
        nm = f"**{name}**" if i == 0 else name
        out.append(f"| {nm} | " + " | ".join(cells) + " |")
    return _wrap("\n".join(out))


# Цветные квадраты итогов попытки (markdown не умеет ANSI — берём эмодзи).
_FUNNEL_EMOJI = {
    "решено": "🟩",
    "неверный ответ": "🟨",
    "ошибка выполнения": "🟧",
    "не компилируется": "🟥",
}
_FUNNEL_BAR_CELLS = 10  # ширина полосы в квадратах (каждый ≈ 10% попыток)


def _emoji_bar(buckets: dict, n: int) -> str:
    """Полоса-отсев квадратами: доли исходов, в сумме ровно на ширину полосы.

    Наибольшие остатки добивают ширину; ненулевая корзина не схлопывается в ноль."""
    from harness.stats.funnel import BUCKETS

    raw = {b: buckets[b] / n * _FUNNEL_BAR_CELLS for b in BUCKETS}
    cells = {b: int(raw[b]) for b in BUCKETS}
    cells = {b: (1 if cells[b] == 0 and buckets[b] else cells[b]) for b in BUCKETS}
    short = _FUNNEL_BAR_CELLS - sum(cells.values())
    for b in sorted(BUCKETS, key=lambda b: raw[b] - int(raw[b]), reverse=True):
        if short <= 0:
            break
        cells[b] += 1
        short -= 1
    return "".join(_FUNNEL_EMOJI[b] * cells[b] for b in BUCKETS)


def render_funnel(result: dict) -> str:
    """Где ломается код у каждой модели (markdown): все попытки по итогу, не баллы.

    Полоса = 100% попыток четырьмя итогами; «решено %» впереди; самая частая поломка —
    отдельной колонкой. Ранжир по доле решённых (как печатает prism leaderboard --full).
    """
    from harness.loaders import load_error_taxonomy
    from harness.stats.funnel import funnel

    rows = funnel(result, load_error_taxonomy())
    head = "| Модель | решено | результат всех попыток | самая частая поломка |"
    sep = "|--------|:---:|:---|:---|"
    out = [head, sep]
    for i, (name, f) in enumerate(rows):
        cause = f["cause"]
        cause_txt = f"{cause[0]} ×{cause[1]}" if cause else "—"
        solved = f"{round(f['solved'] * 100)}%"
        nm = f"**{name}**" if i == 0 else name
        solved = f"**{solved}**" if i == 0 else solved
        out.append(f"| {nm} | {solved} | {_emoji_bar(f['buckets'], f['n'])} | {cause_txt} |")
    return _wrap("\n".join(out))


def _summary_cell(solved: float | None) -> str:
    """Ячейка сводки: полоса 🟩(решено)/🟥(не решено) + процент; «не измерялось» без данных."""
    if solved is None:
        return "_не измерялось_"
    n = round(solved * 10)
    return "🟩" * n + "🟥" * (10 - n) + f" {round(solved * 100)}%"


def render_summary() -> str:
    """Сводная таблица «кто лучше в целом»: доля решённых заданий по A и B рядом.

    «Решено» = задание, где код прошёл ВСЕ скрытые проверки (доля «решено» из funnel — те же
    числа, что в детальных таблицах). Сортировка по A (там данные есть у всех моделей).
    A и B НЕ усредняются: они меряют разное (алгоритмика vs платформа), и разрыв виден."""
    from harness.loaders import load_error_taxonomy
    from harness.stats.funnel import funnel

    tax = load_error_taxonomy()
    a, b = _load("A"), _load("B")
    sa = {name: f["solved"] for name, f in funnel(a, tax)} if a else {}
    sb = {name: f["solved"] for name, f in funnel(b, tax)} if b else {}
    names = sorted(set(sa) | set(sb), key=lambda n: sa.get(n, -1.0), reverse=True)
    out = ["| Модель | Алгоритмика (A) | Платформа 1С (B) |", "|--------|:---|:---|"]
    for i, name in enumerate(names):
        nm = f"**{name}**" if i == 0 else name
        out.append(f"| {nm} | {_summary_cell(sa.get(name))} | {_summary_cell(sb.get(name))} |")
    return _wrap("\n".join(out))


def render_status_summary(a: dict | None, b: dict | None) -> str:
    """Компактная сводка Q̄ A/B по моделям для docs/status.md (ранжир по Q̄ A)."""
    qa = {name: m["Q"] for name, m, _ in _ranked(a)} if a else {}
    qb = {name: m["Q"] for name, m, _ in _ranked(b)} if b else {}
    names = sorted(set(qa) | set(qb), key=lambda n: qa.get(n, -1.0), reverse=True)
    out = ["| Модель | Q · категория A | Q · категория B |", "|---|:---:|:---:|"]
    for i, name in enumerate(names):
        nm = f"**{name}**" if i == 0 else name
        a_txt = f"**{_fmt(qa.get(name), 2)}**" if i == 0 else _fmt(qa.get(name), 2)
        b_txt = f"**{_fmt(qb.get(name), 2)}**" if i == 0 else _fmt(qb.get(name), 2)
        out.append(f"| {nm} | {a_txt} | {b_txt} |")
    return "\n".join(out)


# ── бейджи ───────────────────────────────────────────────────────────────────


def _badge(label: str, value: str, color: str, alt: str) -> str:
    return f'  <img src="https://img.shields.io/badge/{label}-{value}-{color}" alt="{alt}">'


def render_badges() -> str:
    """Счётные бейджи из реальных данных (задач / тест-кейсов / генераций / моделей)."""
    tasks = load_tasks()
    a = [t for t in tasks if t.category == "A"]
    b = [t for t in tasks if t.category == "B"]
    a_cases = sum(len(t.tests.tests) for t in a if t.tests)
    b_proc = 0
    for t in b:  # кат. B: сценарные процедуры в tests.bsl
        p = t.dir / "tests.bsl"
        if p.exists():
            b_proc += len(
                re.findall(r"(?im)^\s*(?:Процедура|Функция)\b", p.read_text(encoding="utf-8"))
            )
    cases = a_cases + b_proc

    res_a, res_b = _load("A"), _load("B")
    models = len({t["model_name"] for r in (res_a, res_b) if r for t in r["tasks"]})
    gens = 0
    for r in (res_a, res_b):
        if not r:
            continue
        exp = PRISM / "results" / f"{r['experiment_id']}.json"
        if exp.exists():
            gens += len(json.loads(exp.read_text(encoding="utf-8"))["task_results"])

    return "\n".join(
        [
            _badge("задач", str(len(tasks)), "success", f"задач: {len(tasks)}"),
            _badge("тест--кейсов", str(cases), "blue", f"тест-кейсов: {cases}"),
            _badge("генераций_в_прогоне", str(gens), "blue", f"генераций: {gens}"),
            _badge("в_лидерборде", f"{models}_моделей", "blue", f"в лидерборде {models} моделей"),
        ]
    )


# ── подстановка в файлы ────────────────────────────────────────────────────────


def _replace_region(text: str, key: str, content: str) -> str:
    """Заменить содержимое между `<!-- prism:KEY -->` и `<!-- /prism:KEY -->`."""
    pat = re.compile(
        rf"(<!-- prism:{re.escape(key)} -->\n).*?(\n<!-- /prism:{re.escape(key)} -->)",
        re.DOTALL,
    )
    if not pat.search(text):
        raise SystemExit(f"в документе нет региона-маркера prism:{key}")
    return pat.sub(lambda m: m.group(1) + content + m.group(2), text)


def write() -> list[Path]:
    """Регенерировать таблицы и бейджи в README.md и docs/status.md. Вернуть изменённые."""
    a, b = _load("A"), _load("B")
    if a is None and b is None:
        raise SystemExit("нет оценок в results/auto/ — сначала `prism score`")

    readme = PRISM / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = _replace_region(text, "badges", render_badges())
    text = _replace_region(text, "lb:summary", render_summary())
    if a:
        text = _replace_region(text, "lb:a-overall", render_overall(a, "A"))
        text = _replace_region(text, "lb:a-skill", render_by_tag(a, "skill", "M"))
        text = _replace_region(text, "lb:a-funnel", render_funnel(a))
    if b:
        text = _replace_region(text, "lb:b-overall", render_overall(b, "B"))
        text = _replace_region(text, "lb:b-platform", render_by_tag(b, "platform", "P"))
        text = _replace_region(text, "lb:b-funnel", render_funnel(b))
    readme.write_text(text, encoding="utf-8")

    changed = [readme]

    # Страница лидерборда сайта (docs/leaderboard.md) — те же регионы, что в README.
    lb_page = PRISM / "docs" / "leaderboard.md"
    if lb_page.exists():
        p = lb_page.read_text(encoding="utf-8")
        if a:
            p = _replace_region(p, "lb:a-overall", render_overall(a, "A"))
            p = _replace_region(p, "lb:a-skill", render_by_tag(a, "skill", "M"))
            p = _replace_region(p, "lb:a-funnel", render_funnel(a))
        if b:
            p = _replace_region(p, "lb:b-overall", render_overall(b, "B"))
            p = _replace_region(p, "lb:b-platform", render_by_tag(b, "platform", "P"))
            p = _replace_region(p, "lb:b-funnel", render_funnel(b))
        lb_page.write_text(p, encoding="utf-8")
        changed.append(lb_page)

    status = PRISM / "docs" / "status.md"
    if status.exists():
        s = status.read_text(encoding="utf-8")
        s = _replace_region(s, "status:lb", render_status_summary(a, b))
        status.write_text(s, encoding="utf-8")
        changed.append(status)
    return changed
