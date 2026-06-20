"""Ось O, исполнительная нога (категория A) — алгоритмическая оптимальность ИСПОЛНЕНИЕМ.

Зачем: в алгоритмике A статический анализатор perf-антипаттернов не находит, и O-авто
у всех упирается в 10 (моделей не различает). Поэтому оптимальность мерится запуском:
решение гоняется на лесенке размеров входа (perf.yaml), число выполненных операций берётся
из oscript -codestat (детерминировано, от машины не зависит), показатель роста p сравнивается
с оптимальным для задачи p_opt. Балл — по отклонению d = p − p_opt (таблица exec_scoring
протокола). Стоимость встроенных команд учитывается подменой (harness/score/cost_model.py).

Гейтинг: нет раннера / нет perf-данных / не нашли функцию → ось не измерена (score=None).
Не исполнился на минимальном размере → None. Таймаут на больших размерах → 2 (слишком медленно).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel

from harness.execute.runner import Runner, get_runner
from harness.loaders import ProtocolL1, TaskPerf
from harness.score.cost_model import HELPERS, instrument
from harness.score.meaning import detect_entry_point

OK_MARKER = "PRISM_O_OK"

# Прогон под -codestat кратно медленнее обычного исполнения (инструментирование счётчика
# + подменённые аналоги встроенных). Лимит выше, чем у оси M (15с), иначе корректные
# O(n²)-решения упираются в таймаут под нагрузкой. Таймаут остаётся сигналом «слишком
# медленно» только для действительно патологических решений (экспонента и т.п.).
O_EXEC_TIMEOUT_S = 60


class OptExecResult(BaseModel):
    """Итог исполнительной оценки O одного кандидата."""

    score: int | None  # балл по exec_scoring; None = ось не измерена
    growth: float | None = None  # показатель роста p (число операций ~ N^p)
    p_opt: float | None = None  # оптимальный показатель для задачи
    ops: list[int] = []  # операций на каждом размере
    sizes: list[int] = []
    entry_point: str | None = None
    note: str = ""


def _subst(snippet: str, n: int, entry: str) -> str:
    return snippet.replace("{n}", str(n)).replace("{entry}", entry)


def _count_ops(stat_path: Path, candidate_lines: int) -> int:
    """Сумма count по строкам ≤ candidate_lines (тело хелперов+кандидата, без генерации входа)."""
    fileinfo = next(iter(json.loads(stat_path.read_text(encoding="utf-8")).values()))
    return sum(
        v["count"]
        for section, lines in fileinfo.items()
        if isinstance(lines, dict)
        for ln, v in lines.items()
        if isinstance(v, dict) and int(ln) <= candidate_lines
    )


def score_o_exec(
    candidate_code: str,
    perf: TaskPerf,
    entry_patterns: list[str],
    protocol: ProtocolL1,
    work_dir: Path,
    name: str = "candidate",
    runner: Runner | None = None,
) -> OptExecResult:
    """Прогнать кандидата на лесенке perf.sizes, оценить класс роста против p_opt."""
    runner = runner or get_runner()
    if not runner.available():
        return OptExecResult(score=None, note=runner.unavailable_reason())

    entry = detect_entry_point(candidate_code, entry_patterns)
    if entry is None:
        return OptExecResult(score=None, note="в коде кандидата не найдено ни одной функции")

    code = HELPERS + "\n" + instrument(candidate_code)  # хелперы + инструментированный кандидат
    candidate_lines = code.count("\n") + 1  # строки тела (генерация входа — ниже)
    work_dir.mkdir(parents=True, exist_ok=True)

    ops, sizes = [], []
    for n in perf.sizes:
        body = (
            _subst(perf.gen, n, entry)
            + "\n"
            + _subst(perf.call, n, entry)
            + f'\nСообщить("{OK_MARKER}");'
        )
        script = work_dir / f"{name}.operf.os"
        stat = work_dir / f"{name}.operf.json"
        stat.unlink(missing_ok=True)
        script.write_text(code + "\n" + body, encoding="utf-8")
        res = runner.run_os_codestat(script, stat, timeout=O_EXEC_TIMEOUT_S)
        if res.timed_out:
            if ops:  # на меньших размерах считалось, а тут завис → слишком медленно
                return OptExecResult(
                    score=protocol.o_exec_scoring().score_for(99.0),
                    growth=None,
                    p_opt=perf.p_opt,
                    ops=ops,
                    sizes=sizes,
                    entry_point=entry,
                    note=f"таймаут на размере {n} — слишком медленно",
                )
            return OptExecResult(
                score=None,
                p_opt=perf.p_opt,
                entry_point=entry,
                note=f"таймаут уже на минимальном размере {n}",
            )
        if OK_MARKER not in res.stdout or not stat.exists():
            return OptExecResult(
                score=None,
                p_opt=perf.p_opt,
                entry_point=entry,
                note=f"не исполнился на размере {n}: {(res.stderr or res.stdout)[-200:].strip()}",
            )
        ops.append(_count_ops(stat, candidate_lines))
        sizes.append(n)

    if len(ops) < 2 or ops[0] <= 0:
        return OptExecResult(
            score=None,
            ops=ops,
            sizes=sizes,
            p_opt=perf.p_opt,
            entry_point=entry,
            note="недостаточно данных для оценки роста",
        )

    growth = math.log(ops[-1] / ops[0]) / math.log(sizes[-1] / sizes[0])
    score = protocol.o_exec_scoring().score_for(growth - perf.p_opt)  # отклонение от оптимума
    return OptExecResult(
        score=score,
        growth=round(growth, 2),
        p_opt=perf.p_opt,
        ops=ops,
        sizes=sizes,
        entry_point=entry,
    )
