"""Ось P (Platform) — корректность обращений к метаданным, ИЗ ИСПОЛНЕНИЯ.

Сигнал — из того же прогона 1С, что и ось M (один запуск, два сигнала):
доля тестов, исполнившихся без платформенной ошибки (clean/total). Платформенная
ошибка = исключение обращения к метаданным/запросу («Поле не найдено», «Объект
не найден», ошибка исполнения запроса) — классификатор в execute/onec/runner.py.
Неверный ответ (FAIL по значению) платформенной ошибкой НЕ считается — это ось M.

Статическая сверка со срезом схемы (v0 концепта) выведена из L1 как анти-валидная
(ρ=−0.27 с экспертом, docs/validity.md) — исполнение её заменяет.
Банды — из metrics/smop_l1_auto.yaml (ось P), код порогов не знает.
"""

from __future__ import annotations

from harness.execute.onec.runner import OneCRunResult
from harness.loaders import ProtocolL1


def score_p(run: OneCRunResult, protocol: ProtocolL1) -> tuple[int | None, dict]:
    """Балл P из результата исполнения кандидата против синтетической базы."""
    if run.status in ("infra_error", "no_result"):       # инфраструктура → «не измерено»
        return None, {"reason": f"исполнение не состоялось ({run.status}): {run.infra_detail[:200]}"}
    if run.status in ("no_entry", "candidate_error"):
        # вина кандидата: функции нет / модуль не компилируется →
        # ни одного подтверждённого обращения к метаданным (pre_check протокола)
        return 0, {"reason": run.infra_detail or "в коде кандидата не найдено ни одной функции",
                   "log": run.log[:200]}

    if run.total == 0:
        # обработчик упал до тестов: платформенные маркеры есть → структура вымышлена
        signal = 0.0 if run.platform_errors else None
        if signal is None:
            return None, {"reason": "тесты не исполнились, платформенных маркеров нет",
                          "log": run.log[:200]}
        return protocol.scoring("P").score_for(signal), {
            "clean_share": 0.0, "platform_errors": run.platform_errors, "log": run.log[:200]}

    clean = run.total - run.platform_error_tests
    share = clean / run.total
    return protocol.scoring("P").score_for(share), {
        "clean_share": round(share, 3),
        "clean": clean,
        "total": run.total,
        "platform_error_tests": run.platform_error_tests,
        "platform_errors": run.platform_errors,
    }
