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


def band(weight: float, protocol: ProtocolL1) -> int:
    """Взвешенная сумма антипаттернов → балл по thresholds оси O из протокола L1."""
    thresholds = protocol.axes["O"].thresholds
    assert thresholds, "у оси O в протоколе L1 должны быть thresholds (машиночитаемые банды)"
    for rule in thresholds:
        if "max_weight" in rule and weight <= rule["max_weight"]:
            return rule["score"]
        if "gt_weight" in rule and weight > rule["gt_weight"]:
            return rule["score"]
    return min(protocol.reachable("O"))          # машина не даёт O=0


def score_o(diagnostics: list[dict], protocol: ProtocolL1) -> tuple[int, dict]:
    """O-авто = «отсутствие известных perf/арх-антипаттернов» (белый список из протокола)."""
    weights = protocol.o_weights()
    hits = [d for d in diagnostics if d["code"] in weights]
    w = sum(weights[d["code"]] for d in hits)
    detail = {"weighted": w, "count": len(hits),
              "codes": sorted({d["code"] for d in hits})}
    return band(w, protocol), detail
