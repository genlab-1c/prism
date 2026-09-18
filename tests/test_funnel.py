"""Тест воронки отказа (harness/stats/funnel.py).

Главное — АТРИБУЦИЯ К КОРНЮ: причина считается там, где прогон впервые умер, без
двойного счёта каскада; ворота кат. A (BSL LS / OneScript) и кат. B (1С) дают один
общий набор этапов разбор→запуск→верно. Эти числа публикуются, поэтому под тестом.
"""

from __future__ import annotations

from harness.loaders import load_error_taxonomy
from harness.stats.funnel import bucket_of, funnel, run_outcome

TAX = load_error_taxonomy()


def _run(task_id: str, detail: dict, scores: dict | None = None) -> dict:
    return {"task_id": task_id, "scores": scores or {"S": 10}, "detail": detail}


# ── кат. B: разбор и компиляция слиты в /CheckModules ─────────────────────────


def test_b_candidate_error_dies_at_parse():
    o = run_outcome(
        _run(
            "B1",
            {
                "S": {"root_causes": 3},
                "M": {"status": "candidate_error", "compile_errors": ["Ожидается символ ';'"]},
            },
        ),
        TAX,
    )
    assert o["reached"] == 0 and o["died"] == "разбор"
    assert o["code"] == "S.COMPILE"  # текст классифицирован, не корзина по умолчанию


def test_b_no_entry_dies_at_run():
    o = run_outcome(_run("B1", {"S": {"root_causes": 0}, "M": {"status": "no_entry"}}), TAX)
    assert o["reached"] == 1 and o["died"] == "запуск" and o["code"] == "M.NOENTRY"


def test_b_platform_error_is_metadata_not_wrong():
    """Платформенная причина ловится структурой (platform_errors), не текстом."""
    o = run_outcome(
        _run(
            "B1",
            {
                "S": {"root_causes": 0},
                "M": {
                    "status": "ok",
                    "passed": 0,
                    "total": 3,
                    "platform_errors": ["Поле не найдено"],
                    "platform_error_tests": 3,
                },
            },
        ),
        TAX,
    )
    assert o["died"] == "верно" and o["code"] == "P.METADATA"


def test_b_full_pass_survives():
    o = run_outcome(
        _run("B1", {"S": {"root_causes": 0}, "M": {"status": "ok", "passed": 3, "total": 3}}), TAX
    )
    assert o["reached"] == 3 and o["died"] is None


# ── кат. A: BSL LS (разбор) отдельно от OneScript (запуск) ────────────────────


def test_a_parse_ok_but_onescript_compile_dies_at_run():
    """BSL LS разобрал, но OneScript не собрал — смерть на запуске, не на разборе."""
    o = run_outcome(
        _run(
            "A1",
            {
                "S": {"root_causes": 0},
                "M": {
                    "executed": False,
                    "entry_point": "Ф",
                    "errors": ["Error / Identifier expecting"],
                },
            },
        ),
        TAX,
    )
    assert o["reached"] == 1 and o["died"] == "запуск" and o["code"] == "S.COMPILE"


def test_a_ran_but_wrong_answer_is_wrong_not_runtime():
    """Отработал без исключения, но тесты не прошли → тихо неверный результат."""
    o = run_outcome(
        _run(
            "A1",
            {
                "S": {"root_causes": 0},
                "M": {"executed": True, "entry_point": "Ф", "passed": 1, "total": 3, "errors": []},
            },
        ),
        TAX,
    )
    assert o["died"] == "верно" and o["code"] == "M.WRONG"


# ── агрегация модели и каскад ─────────────────────────────────────────────────


def test_no_double_count_of_cascade():
    """Не скомпилировался → причина одна (разбор), а не +M/+P/+O. Доли кумулятивны."""
    result = {
        "tasks": [
            {
                "model_id": "m",
                "model_name": "M",
                "task_id": "B1",
                "runs": [
                    {
                        "scores": {"S": 0},
                        "detail": {
                            "S": {"root_causes": 2},
                            "M": {
                                "status": "candidate_error",
                                "compile_errors": ["Неопознанный оператор"],
                            },
                        },
                    },
                    {
                        "scores": {"S": 10},
                        "detail": {
                            "S": {"root_causes": 0},
                            "M": {"status": "ok", "passed": 3, "total": 3},
                        },
                    },
                ],
            }
        ]
    }
    ((name, f),) = funnel(result, TAX)
    assert f["n"] == 2
    assert f["reach"]["разбор"] == 0.5  # 1 из 2 прошёл разбор
    assert f["reach"]["верно"] == 0.5  # тот же 1 дожил до конца
    assert f["buckets"] == {
        "решено": 1,
        "неверный ответ": 0,
        "ошибка выполнения": 0,
        "не компилируется": 1,
        "не измерено": 0,
    }
    assert f["solved"] == 0.5
    assert f["cause"] == ("ошибка синтаксиса", 1)  # единственная смерть, причина названа


def test_infra_failure_is_visible_and_not_blamed_on_the_model():
    """Сбой окружения получает свою корзину и вину infra, а не выпадает из воронки.

    Раньше такой прогон возвращал None и просто исчезал: доли считались от меньшего
    знаменателя, и инфраструктурный сбой становился невидимым (F17 плана гигиены).
    """
    out = run_outcome(_run("B1", {}, scores={"S": None}), TAX)
    assert out is not None
    assert out["blame"] == "infra" and bucket_of(out) == "не измерено"
    assert out["code"].startswith("INFRA.")


def test_wall_clock_timeout_is_infra_but_burnt_cpu_budget_is_not():
    """Два исхода, которые раньше сливались в один «таймаут», и вина у них разная.

    Сторож по НАСТЕННЫМ часам срабатывает, когда окружение зависло, — это «не измерено».
    Бюджет ПРОЦЕССОРНОГО времени жжёт сам кандидат — это его вина (протокол 1.4.0).
    """
    stalled = _run("A1", {"M": {"timed_out": True}}, scores={"S": None})
    assert run_outcome(stalled, TAX)["blame"] == "infra"

    burnt = _run(
        "A1",
        {
            "S": {"root_causes": 0},
            "M": {"timed_out": True, "cpu_exhausted": True, "executed": False},
        },
        scores={"S": 10},
    )
    assert run_outcome(burnt, TAX)["blame"] == "model"


def test_model_failures_keep_their_blame():
    """Обычный провал кода остаётся на модели — метка вины не размывает ответственность."""
    broken = _run("A1", {"S": {"root_causes": 2, "errors": ["Пропущен символ"]}}, scores={"S": 6})
    assert run_outcome(broken, TAX)["blame"] == "model"
