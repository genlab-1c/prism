"""Ось O (Optimization), категория A — O-авто по статическим perf/арх-антипаттернам.

Петля (протокол L1, metrics/smop_l1_auto.yaml, ось O):
 1. Из диагностик BSL LS берутся только коды из БЕЛОГО СПИСКА весов (weights):
    perf/арх-релевантные (ВТ без параметров, соединение с подзапросом, …).
    Стилевой шум (MagicNumber, LineLength) сознательно исключён — он
    антикоррелировал с экспертной «оптимальностью».
 2. w = взвешенная сумма сработавших; балл — по thresholds оси O из протокола.

ВАЖНО (coverage протокола): это O-АВТО — «отсутствие известных антипаттернов».
Архитектурная оптимальность (выбор алгоритма, ВТ vs ГДЕ) статике невидима → это
Уровень 2 (эксперт). Поэтому машина не ставит O=0 (честный предел инструмента).

Диагностики даёт harness/execute/bsl_ls.py (тот же батч, что и для оси S).
"""

from __future__ import annotations

from harness.loaders import ProtocolL1


def score_o(diagnostics: list[dict], protocol: ProtocolL1) -> tuple[int, dict]:
    """O-авто = «отсутствие известных perf/арх-антипаттернов» (white_list из протокола)."""
    weights = protocol.o_weights()
    hits = [d for d in diagnostics if d["code"] in weights]
    w = sum(weights[d["code"]] for d in hits)
    detail = {"weighted": w, "count": len(hits), "codes": sorted({d["code"] for d in hits})}
    return protocol.scoring("O").score_for(
        w
    ), detail  # нижняя граница O = 2, не 0: машина видит лишь короткий список антипаттернов
