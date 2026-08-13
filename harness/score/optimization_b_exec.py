"""Ось O, исполнительная нога КАТЕГОРИИ B — оптимальность обращений к данным ИСПОЛНЕНИЕМ.

Близнец optimization_exec.py (категория A): там вход — растущий массив, единица работы — шаг
кода (oscript -codestat); здесь вход — растущая БАЗА, единица работы — поход в СУБД (техжурнал 1С).
Кандидат гоняется на лесенке perf.sizes (размер синтетической базы), число обращений к данным,
атрибутированных кандидату по Context, берётся из perf_run.measure_db_ops. Показатель роста p
сравнивается с p_opt задачи (эталон набором → p≈0). Балл — по таблице b_exec_scoring протокола L1.

Гейтинг (как у A): нет образа/раннера или замер не состоялся на размере → ось не измерена (None),
НЕ ноль. Метрика роста задаётся perf.count — либо число ОБРАЩЕНИЙ ("sdbl" по умолчанию,
"register"), либо число поднятых СТРОК ("rows", "reg_rows"). Первое семейство ловит «N+1»,
второе — «подними всё и разберись в коде»: походов столько же, а объём растёт. Автоотката
между семействами нет: нулевой счётчик на минимальном размере → N/A.
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
    metric: str = ""  # по какому счётчику мерили рост: sdbl | reg_reads | rows | reg_rows
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

    # метрика роста (perf.count) — ЧТО именно растёт. Два семейства, ловят разные пороки:
    #   ЧИСЛО ОБРАЩЕНИЙ — порок «N+1» (запрос или чтение через точку в цикле):
    #     sdbl     — все логические обращения к данным (дефолт: одно правило на все задачи);
    #     register — только чтения физтаблиц регистров (без шума для регистровых задач);
    #   ЧИСЛО СТРОК — порок «подними всё и разберись в коде» (походов столько же, объём растёт):
    #     rows     — строки по всем операторам кандидата (годится и там, где регистров нет);
    #     reg_rows — строки только из физтаблиц регистров.
    # Строчные метрики применимы, ТОЛЬКО если у правильного решения ответ ограничен: когда
    # perf.grow доращивает базу внутрь запрашиваемого множества, результат эталона растёт сам
    # и рост строк — свойство задачи, а не порок (см. память cat-b-o-rows-metric).
    count_mode = perf.get("count", "sdbl")
    by_mode = {
        "sdbl": ("sdbl", [m.cand_sdbl for m in measured]),
        "register": ("reg_reads", [m.cand_reg_reads for m in measured]),
        "rows": ("rows", [m.cand_rows for m in measured]),
        "reg_rows": ("reg_rows", [m.cand_reg_rows for m in measured]),
    }
    metric, counts = by_mode.get(count_mode, by_mode["sdbl"])

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
    # Шкала — под счётчик: рост объёма судится мягче роста числа обращений (см. протокол).
    score = protocol.o_b_scoring_for(count_mode).score_for(growth - p_opt)
    return OptBExecResult(
        score=score,
        growth=round(growth, 3),
        p_opt=p_opt,
        metric=metric,
        counts=counts,
        sizes=sizes,
    )
