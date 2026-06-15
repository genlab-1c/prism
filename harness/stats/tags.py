"""Срезы качества по тегам задач: «где модель сильнее/слабее».

Правила агрегации (см. обсуждение в docs/status.md):
 1. ПО ОСЯМ, не по Q — заголовок M (логика работает), для platform-тегов ещё P;
    Q подмешала бы почти всегда-10 S и размазала сигнал.
 2. ДВА ЭТАПА, равный вес на задачу: прогоны → балл задачи (среднее по runs),
    задачи → тег как МАКРО-среднее (каждая задача весит одинаково). Иначе задача
    с большим числом тестов задавит остальные.
 3. Всегда с n — тег на 1–2 задачах это шум; печатаем n рядом со средним.
 4. Читать модель-vs-модель: абсолютное «тег трудный» спутано со сложностью задач,
    но сравнение моделей внутри тега честно (одни и те же задачи).

Мультизначность не двоит криво: задача с тегами [запрос, метаданные] честно входит
в оба среза. Вход — структура auto_l1 (как пишет orchestrate) + теги из задач.
"""

from __future__ import annotations

from statistics import mean

from harness.loaders import Task

AXES = ("S", "M", "O", "P")


def _task_axis_means(runs: list[dict]) -> dict[str, float | None]:
    """Этап 1: прогоны → балл задачи по каждой оси (среднее измеренных, None-исключаются)."""
    out: dict[str, float | None] = {}
    for axis in AXES:
        vals = [r["scores"].get(axis) for r in runs]
        vals = [v for v in vals if v is not None]
        out[axis] = mean(vals) if vals else None
    return out


def tag_profile(model_tasks: list[dict], tasks_by_id: dict[str, Task]) -> dict[str, dict]:
    """Профиль одной модели по тегам.

    model_tasks — список групп {task_id, runs:[...]} одной модели (как в auto_l1).
    Возврат: {измерение: {тег: {axis: среднее|None, "n": число задач}}}.
    """
    # Этап 1: балл каждой задачи по осям
    per_task = {g["task_id"]: _task_axis_means(g["runs"]) for g in model_tasks}

    # Этап 2: макро-среднее по задачам внутри каждого тега каждого измерения
    profile: dict[str, dict] = {}
    for task_id, axis_means in per_task.items():
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        for dim, values in (task.tags or {}).items():
            dim_bucket = profile.setdefault(dim, {})
            for tag in values:
                tag_bucket = dim_bucket.setdefault(tag, {a: [] for a in AXES})
                for axis in AXES:
                    if axis_means[axis] is not None:
                        tag_bucket[axis].append(axis_means[axis])

    # свернуть списки в средние + n (n = число задач с измеренной осью M, опорная ось)
    result: dict[str, dict] = {}
    for dim, tags in profile.items():
        result[dim] = {}
        for tag, axis_lists in tags.items():
            row = {a: (round(mean(v), 2) if v else None) for a, v in axis_lists.items()}
            row["n"] = len(axis_lists["M"])      # задач, где ось M измерена (опорная)
            result[dim][tag] = row
    return result


def format_tag_profile(model_name: str, profile: dict[str, dict]) -> str:
    """Человекочитаемый профиль: измерение → теги с M̄/P̄ и n."""
    lines = [f"профиль по тегам — {model_name}"]
    for dim in sorted(profile):
        lines.append(f"  [{dim}]")
        lines.append(f"    {'тег':<22} {'M̄':>5} {'P̄':>5} {'n':>3}")
        rows = sorted(profile[dim].items(), key=lambda kv: (-(kv[1].get('M') or -1), kv[0]))
        for tag, row in rows:
            m = "—" if row.get("M") is None else f"{row['M']:.1f}"
            p = "—" if row.get("P") is None else f"{row['P']:.1f}"
            warn = " ⚠малое n" if row["n"] < 3 else ""
            lines.append(f"    {tag:<22} {m:>5} {p:>5} {row['n']:>3}{warn}")
    return "\n".join(lines)
