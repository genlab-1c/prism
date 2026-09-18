"""Ось P (Platform) — корректность обращений к метаданным, ИЗ ИСПОЛНЕНИЯ.

Сигнал — из того же прогона 1С, что и ось M (один запуск, два сигнала):
доля тестов, исполнившихся без платформенной ошибки (clean/judged). Платформенная
ошибка = исключение обращения к МЕТАДАННЫМ («Поле не найдено», «Объект не найден»,
неверные параметры виртуальной таблицы). Словарь маркеров и подклассов живёт в
metrics/error_taxonomy.yaml, решение по сегменту — platform_verdict в execute/onec/runner.py.
Не считаются провалом P: неверный ответ (FAIL по значению) и кривой текст запроса —
оба про ось M. Тест, чей запрос не разобрался грамматически, до имён метаданных не дошёл
и свидетельства не дал: он выбрасывается из ЗНАМЕНАТЕЛЯ (judged), а не идёт в числитель.

Раньше P проверяли статически — сверкой имён со срезом схемы. Тот вариант коррелировал
с оценкой эксперта ОТРИЦАТЕЛЬНО (корреляция Спирмена ρ=−0.27), то есть мерил скорее
наоборот, поэтому убран из L1 (см. docs/validity.md). Исполнение его заменяет.
Банды — из metrics/smop_l1_auto.yaml (ось P), код порогов не знает.
"""

from __future__ import annotations

from harness.execute.onec.runner import OneCRunResult, platform_verdict
from harness.loaders import ProtocolL1

# Хвост лога в детали оси P — для чтения человеком; полный лог лежит в detail.M.
LOG_DETAIL = 400


def score_p(run: OneCRunResult, protocol: ProtocolL1) -> tuple[int | None, dict]:
    """Балл P из результата исполнения кандидата против синтетической базы."""
    if run.status in ("infra_error", "no_result"):  # инфраструктура → «не измерено»
        return None, {
            "reason": f"исполнение не состоялось ({run.status}): {run.infra_detail[:200]}"
        }
    if run.status in ("no_entry", "candidate_error"):
        # Функции нет либо модуль не компилируется. Раньше здесь стоял ноль по правилу
        # «ни одного подтверждённого обращения к метаданным». Но ноль утверждает, что
        # обращения были и оказались неверными, а их просто не проверяли: модуль с одной
        # синтаксической опечаткой мог ссылаться на метаданные безупречно. Оси SMOP
        # независимы по смыслу, а у P и M один канал измерения — прогон 1С; молчание
        # канала это отсутствие свидетельства, а не свидетельство против.
        # Вина кандидата уже наказана там, где она измерена: S за несобираемость, M за
        # непройденные тесты. Неполнота видна в охвате осей рядом с Q.
        return None, {
            "reason": "не измерено: модуль не дошёл до базы, "
            + (run.infra_detail or "ни одно обращение к метаданным не проверено"),
            "unmeasured": run.status,
            "log": run.log[:LOG_DETAIL],
        }

    if run.total == 0:
        # Обработчик упал до тестов. Ноль тут уместен, только если упал он ИМЕННО на
        # обращении к метаданным. Сырого наличия маркера мало: под «(Выполнить)» лежит и
        # неразобравшийся текст запроса, а его правило judged велит из счёта выбрасывать.
        # Поэтому спрашиваем тот же вердикт, что и по отдельным тестам.
        if platform_verdict(run.log) != "fault":
            return None, {
                "reason": "не измерено: тесты не исполнились, обращений к метаданным не видно",
                "unmeasured": "crashed_before_tests",
                "platform_errors": run.platform_errors,
                "log": run.log[:LOG_DETAIL],
            }
        return protocol.scoring("P").score_for(0.0), {
            "clean_share": 0.0,
            "platform_errors": run.platform_errors,
            "log": run.log[:LOG_DETAIL],
        }

    # Тесты, где запрос не разобрался грамматически, свидетельства не дали: платформа до
    # проверки имён не дошла. Они не «чистые» (иначе P=10 за непроверенное) и не «провал»
    # (иначе штраф дважды за одну кривую строку) — их просто нет в доле.
    judged = run.total - run.unverified_tests
    if judged <= 0:
        return None, {
            "reason": "не измерено: ни один тест не дошёл до обращения к метаданным",
            "unmeasured": "query_never_parsed",
            "total": run.total,
            "unverified_tests": run.unverified_tests,
            "log": run.log[:LOG_DETAIL],
        }
    # Техжурнал знает то, чего не знает лог тестов: доходил ли код кандидата до данных.
    # Без этого «чистым» считался и тест, упавший на общем BSL раньше первого запроса, —
    # 36 записей корпуса получали P=10 при полностью провалившихся тестах. Ноль здесь тоже
    # не годится: обращений не было, значит и неверными они быть не могли.
    if run.db_touched is False and not run.platform_error_tests:
        return None, {
            "reason": "не измерено: код кандидата ни разу не обратился к данным (техжурнал)",
            "unmeasured": "no_db_access",
            "total": run.total,
            "log": run.log[:LOG_DETAIL],
        }
    clean = judged - run.platform_error_tests
    share = clean / judged
    return protocol.scoring("P").score_for(share), {
        "db_touched": run.db_touched,
        "clean_share": round(share, 3),
        "clean": clean,
        "judged": judged,
        "total": run.total,
        "unverified_tests": run.unverified_tests,
        "platform_error_tests": run.platform_error_tests,
        "platform_errors": run.platform_errors,
    }
