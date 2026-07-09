"""Ось O, исполнительная нога КАТЕГОРИИ B — оптимальность обращений к данным ИСПОЛНЕНИЕМ.

Близнец optimization_exec.py (категория A): там вход — растущий массив, единица работы — шаг
кода (oscript -codestat); здесь вход — растущая БАЗА, единица работы — поход в СУБД (техжурнал 1С).
Кандидат гоняется на лесенке perf.sizes (размер синтетической базы), число обращений к данным,
атрибутированных кандидату по Context, берётся из perf_run.measure_db_ops. Показатель роста p
сравнивается с p_opt задачи (эталон набором → p≈0). Балл — по таблице b_exec_scoring протокола L1.

Гейтинг (как у A): нет образа/раннера или замер не состоялся на размере → ось не измерена (None),
НЕ ноль. Метрика роста задаётся perf.count: по умолчанию "sdbl" (все логические обращения к данным —
ловит цикл по любому объекту, одно правило на все задачи); "register" — только чтения физтаблиц
регистров (чище для регистровых задач). Автоотката нет: при "register" и нуле обращений → N/A.
"""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel

from harness.execute.onec.perf_run import measure_db_ops
from harness.loaders import ProtocolL1


class OptBExecResult(BaseModel):
    """Итог исполнительной оценки O одного кандидата категории B."""

    score: int | None  # балл по b_exec_scoring; None = ось не измерена
    growth: float | None = None  # показатель роста p (обращения ~ база^p)
    p_opt: float | None = None
    metric: str = ""  # по какому счётчику мерили рост: reg_reads | sdbl
    counts: list[int] = []
    sizes: list[int] = []
    entry_point: str | None = None
    note: str = ""


def score_o_b_exec(
    candidate_code: str,
    task_dir: Path,
    perf: dict,
    protocol: ProtocolL1,
    work_dir: Path,
    entry_patterns: list[str],
) -> OptBExecResult:
    """Прогнать кандидата на лесенке perf.sizes (размер базы), оценить класс роста обращений к СУБД."""
    if not isinstance(perf, dict):
        perf = perf.model_dump()  # TaskPerf (из конвейера) → dict
    sizes = list(perf.get("sizes") or [])
    p_opt = float(perf.get("p_opt", 0.0))
    if len(sizes) < 2:
        return OptBExecResult(score=None, p_opt=p_opt, note="perf.sizes: нужно ≥2 размеров базы")

    measured = []
    for n in sizes:
        r = measure_db_ops(candidate_code, task_dir, perf, n, work_dir / f"n{n}", entry_patterns)
        if not r.ok:
            return OptBExecResult(
                score=None,
                p_opt=p_opt,
                entry_point=None,
                note=f"замер не состоялся на размере базы {n}: {r.note or r.result[:120]}",
            )
        measured.append(r)

    # метрика роста (perf.count): по умолчанию "sdbl" — все логические обращения к данным
    # (общий случай, ловит цикл по любому объекту); "register" — только чтения физтаблиц
    # регистров (прицельно и без шума для регистровых задач). Дефолт sdbl: одно правило на всё.
    count_mode = perf.get("count", "sdbl")
    if count_mode == "register":
        metric, counts = "reg_reads", [m.cand_reg_reads for m in measured]
    else:
        metric, counts = "sdbl", [m.cand_sdbl for m in measured]

    if counts[0] <= 0:
        return OptBExecResult(
            score=None,
            p_opt=p_opt,
            metric=metric,
            counts=counts,
            sizes=sizes,
            note=f"кандидат не обратился к данным (счётчик {metric}) на минимальном размере",
        )

    growth = math.log(counts[-1] / counts[0]) / math.log(sizes[-1] / sizes[0])
    score = protocol.o_b_exec_scoring().score_for(growth - p_opt)
    return OptBExecResult(
        score=score,
        growth=round(growth, 3),
        p_opt=p_opt,
        metric=metric,
        counts=counts,
        sizes=sizes,
    )
