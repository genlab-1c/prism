"""Тесты аудита корпуса (harness/audit.py).

Проверяется не «красиво ли печатает», а сами инварианты: на синтетическом корпусе из
нескольких записей каждый пункт должен поймать ровно свою аномалию. Корпус собирается
файлами, как настоящий: рулон генерации + файл оценок.
"""

from __future__ import annotations

import json

import pytest

from harness import audit


def write_corpus(tmp_path, pairs, auto_runs=None):
    """Рулон и оценки из компактного описания.

    pairs — [(задача, id, имя, {поля прогона})]; auto_runs — [(задача, id, имя, {оценки/detail})].
    По умолчанию оценки зеркалят рулон с пустыми баллами.
    """
    exp = {
        "experiment_name": "experiment_X_20260101_000000",
        "task_results": [
            {
                "task_id": t,
                "model_id": mid,
                "model_name": name,
                "runs": [
                    {
                        "run_index": 0,
                        "response": fields.get("response", "Функция Ф() КонецФункции"),
                        "response_hash": fields.get("hash", "h1"),
                        "tokens_output": fields.get("tokens_output", 10),
                        "max_tokens": fields.get("max_tokens", 65536),
                        "provenance": fields.get("provenance", ""),
                        "generated_at": fields.get("generated_at", "2026-09-09T00:00:00"),
                        "success": fields.get("success", True),
                        "error": fields.get("error"),
                    }
                ],
            }
            for t, mid, name, fields in pairs
        ],
    }
    auto = {
        "protocol_version": "1.3.0",
        "constitution_version": "1.2.0",
        "tasks": [
            {
                "task_id": t,
                "model_id": mid,
                "model_name": name,
                "runs": [
                    {
                        "run_index": 0,
                        "response_hash": fields.get("hash", "h1"),
                        "scores": fields.get(
                            "scores", {"S": 10, "M": 10.0, "O": 10, "P": None, "Q": 10.0}
                        ),
                        "detail": fields.get(
                            "detail", {"S": {}, "M": {"entry_point": "Ф"}, "O": {"leg": "O-исп"}}
                        ),
                    }
                ],
            }
            for t, mid, name, fields in (auto_runs if auto_runs is not None else pairs)
        ],
    }
    ep = tmp_path / "experiment_X.json"
    ap = tmp_path / "experiment_X_auto_l1.json"
    ep.write_text(json.dumps(exp, ensure_ascii=False), encoding="utf-8")
    ap.write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
    return ep, ap


def corpus(tmp_path, pairs, auto_runs=None, category="A"):
    ep, ap = write_corpus(tmp_path, pairs, auto_runs)
    return audit.load_corpus(category, experiment=ep, auto=ap)


def texts(section):
    return " | ".join(t for _, t in section["items"])


def statuses(section):
    return [st for st, _ in section["items"]]


# ── связка рулона и оценок ───────────────────────────────────────────────────


def test_duplicate_scores_pick_the_one_matching_the_roll(tmp_path):
    """Две оценки на одну генерацию: живая та, чей хеш совпал с рулоном; вторая — дубль."""
    pairs = [("T1", "new/id", "Модель", {"hash": "живой"})]
    auto = [
        (
            "T1",
            "old/id",
            "Модель",
            {"hash": "", "scores": {"S": 10, "M": 0.0, "O": None, "P": 0.0, "Q": 3.3}},
        ),
        ("T1", "new/id", "Модель", {"hash": "живой"}),
    ]
    c = corpus(tmp_path, pairs, auto)
    assert len(c["records"]) == 1
    assert c["records"][0]["model_id_auto"] == "new/id"
    assert [d["model_id"] for d in c["dups"]] == ["old/id"]


def test_orphan_scores_without_generation(tmp_path):
    """Оценка без пары в рулоне — сирота, в записи корпуса не попадает."""
    c = corpus(tmp_path, [("T1", "id", "Модель", {})], [("T9", "id", "Модель", {})])
    assert c["records"] == []
    assert [o["key"][0] for o in c["orphans"]] == ["T9"]


def test_hash_mismatch_is_reported(tmp_path):
    """Оценка посчитана по другому ответу — хеши разошлись."""
    pairs = [("T1", "id", "Модель", {"hash": "ответ-2"})]
    auto = [("T1", "id", "Модель", {"hash": "ответ-1"})]
    c = corpus(tmp_path, pairs, auto)
    sec = audit._section_linkage([c])
    assert "хеши разошлись" in sec["details"]
    assert "разошлись) — 1" in texts(sec)


def test_legacy_o_schema_detected(tmp_path):
    """Записи без поля leg и с легаси-полем gated требуют пересчёта."""
    pairs = [
        ("T1", "id", "М1", {"detail": {"O": {"weighted": 0}}}),
        ("T2", "id", "М2", {"detail": {"O": {"leg": "O-исп", "gated": True}}}),
    ]
    c = corpus(tmp_path, pairs)
    sec = audit._section_linkage([c])
    assert "без поля leg — 1" in texts(sec)
    assert "gated — 1" in texts(sec)


# ── условия прогона ──────────────────────────────────────────────────────────


def test_ceiling_and_empty_response(tmp_path):
    """Ответ, упёршийся в потолок, и пустой ответ при успешном вызове."""
    pairs = [
        ("T1", "id", "М1", {"tokens_output": 4096, "max_tokens": 4096, "response": ""}),
        ("T2", "id", "М2", {"tokens_output": 100, "max_tokens": 65536}),
        ("T3", "id", "М3", {"max_tokens": 0}),
    ]
    c = corpus(tmp_path, pairs)
    sec = audit._section_provenance([c])
    assert "потолок (обрыв по длине) — 1" in texts(sec)
    assert "пустой ответ при успешном вызове — 1" in texts(sec)
    assert "нет max_tokens) — 1 из 3" in texts(sec)


def test_known_conditions_are_ok(tmp_path):
    """Корпус с единым потолком и без обрывов нарушений не даёт."""
    c = corpus(tmp_path, [("T1", "id", "М", {})])
    sec = audit._section_provenance([c])
    assert statuses(sec) == ["ok", "ok", "ok", "ok"]


# ── ответ без кода против оси S ──────────────────────────────────────────────


def test_no_declaration_with_positive_s(tmp_path):
    """Текст без объявления не должен получать положительный S."""
    pairs = [
        (
            "T1",
            "id",
            "М1",
            {
                "response": "МассивСредних = Новый Массив;",
                "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
            },
        ),
        ("T2", "id", "М2", {"response": "Функция Ф() КонецФункции"}),
    ]
    c = corpus(tmp_path, pairs)
    sec = audit._section_no_code([c])
    assert "положительный — 1 из 1" in texts(sec)


def test_declaration_without_detected_entry_point(tmp_path):
    """Объявление есть, а точку входа скорер не нашёл — слепое пятно детектора.

    Проверка идёт по факту из detail, а не по регэкспу аудита: иначе при правке детектора
    аудит начнёт мерить не то, что сделал скорер.
    """
    pairs = [
        (
            "T1",
            "id",
            "М1",
            {
                "response": "Процедура П(А)\n Возврат;\nКонецПроцедуры",
                "detail": {"M": {"entry_point": None}, "O": {"leg": "O-исп"}},
            },
        ),
        (
            "T2",
            "id",
            "М2",
            {
                "response": "Функция Ф() КонецФункции",
                "detail": {"M": {"entry_point": "Ф"}, "O": {"leg": "O-исп"}},
            },
        ),
    ]
    c = corpus(tmp_path, pairs, category="A")
    sec = audit._section_no_code([c])
    assert "точка входа не найдена — 1" in texts(sec)
    assert any(
        "только процедура" in line
        for line in sec["details"]["точка входа не найдена при наличии объявления"]
    )


def test_category_b_clean_module_with_uncallable_declaration(tmp_path):
    """Кат. B: модуль собрался чисто, объявление есть, а позвать нечего — слепота обвязки.

    Компилятор теперь запускается и при отсутствии точки входа, поэтому S=10 сам по себе
    не нарушение. Нарушение — когда функция в коде ЕСТЬ, а прогон её не нашёл.
    """
    pairs = [
        (
            "B1",
            "id",
            "М",
            {
                "response": "function ПолучитьОборот(Счёт) Экспорт\n Возврат 1;\nКонецФункции",
                "scores": {"S": 10, "M": 0.0, "O": None, "P": 0.0, "Q": 3.3},
                "detail": {
                    "S": {"instrument": "1С /CheckModules"},
                    "M": {"status": "no_entry"},
                    "O": {"leg": "O-авто"},
                },
            },
        )
    ]
    c = corpus(tmp_path, pairs, category="B")
    sec = audit._section_no_code([c])
    assert "позвать нечего — 1" in texts(sec)


def test_infra_failure_not_counted_as_detector_blindness(tmp_path):
    """Прогон не состоялся — точки входа нет по инфраструктурной причине, а не по слепоте."""
    pairs = [
        (
            "B2",
            "id",
            "М2",
            {
                "response": "Функция Ф() КонецФункции",
                "scores": {"S": None, "M": None, "O": None, "P": None, "Q": None},
                "detail": {
                    "S": {"reason": "исполнение не состоялось (no_result)"},
                    "M": {"reason": "исполнение не состоялось (no_result)"},
                    "O": {"leg": "O-исп-B"},
                },
            },
        )
    ]
    c = corpus(tmp_path, pairs, category="B")
    sec = audit._section_no_code([c])
    assert "точка входа не найдена — 0" in texts(sec)


# ── ось O ────────────────────────────────────────────────────────────────────


def test_o_not_measured_while_code_ran(tmp_path):
    """Код прошёл тесты, а замер O не состоялся — подозрение на обвязку замера."""
    pairs = [
        (
            "T1",
            "id",
            "М1",
            {
                "scores": {"S": 10, "M": 10.0, "O": None, "P": None, "Q": 10.0},
                "detail": {
                    "O": {
                        "leg": "O-исп",
                        "note": "не исполнился на размере 200: Symbol not found Колонки",
                    }
                },
            },
        ),
        (
            "T2",
            "id",
            "М2",
            {
                "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
                "detail": {
                    "O": {"leg": "O-исп", "note": "не исполнился на размере 200: Method not found"}
                },
            },
        ),
    ]
    c = corpus(tmp_path, pairs)
    sec = audit._section_optimization([c])
    assert "замер O не состоялся — 1" in texts(sec)
    assert "при M ≥ 5" in texts(sec)


def test_na_reasons_are_grouped(tmp_path):
    """Причины неизмеренной O различимы: гейт по M против несостоявшегося замера."""
    pairs = [
        (
            "T1",
            "id",
            "М1",
            {
                "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
                "detail": {
                    "O": {"leg": "O-исп", "gated_by_m": True, "note": "оптимальность не оцениваем"}
                },
            },
        ),
        (
            "T2",
            "id",
            "М2",
            {
                "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
                "detail": {"O": {"leg": "O-исп", "note": "не исполнился на размере 300: ошибка"}},
            },
        ),
    ]
    c = corpus(tmp_path, pairs)
    sec = audit._section_optimization([c])
    reasons = sec["details"]["причины неизмеренной O"]
    assert any("гейт по M < 5: 1" in r for r in reasons)
    assert any("не исполнился на размере N: 1" in r for r in reasons)


# ── оси M и P ────────────────────────────────────────────────────────────────


def _b_rec(task, log, scores):
    return (
        task,
        "id",
        f"М{task}",
        {
            "scores": scores,
            "detail": {
                "S": {},
                "M": {"status": "ok", "log": log, "platform_errors": [], "platform_error_tests": 0},
                "O": {"leg": "O-авто"},
                "P": {"total": 1, "platform_error_tests": 0},
            },
        },
    )


def test_query_syntax_separated_from_metadata(tmp_path):
    """Под общим маркером различаются авторство запроса (ось M) и метаданные (ось P)."""
    meta = _b_rec(
        "B1",
        'тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): Поле не найдено "Склад"',
        {"S": 10, "M": 0.0, "O": None, "P": 0.0, "Q": 3.3},
    )
    syntax = _b_rec(
        "B2",
        'тест1 ИСКЛЮЧЕНИЕ: Ошибка при вызове метода контекста (Выполнить): Синтаксическая ошибка "И"',
        {"S": 10, "M": 0.0, "O": None, "P": 0.0, "Q": 3.3},
    )
    c = corpus(tmp_path, [meta, syntax], category="B")
    sec = audit._section_platform([c])
    assert "ось M) — 1" in texts(sec)
    assert "ось P) — 1" in texts(sec)
    assert "про текст запроса — 1" in texts(sec)


def test_platform_error_swallowed_by_fail(tmp_path):
    """Платформенная ошибка, записанная тестом как FAIL, в балл P не попадает."""
    rec = _b_rec(
        "B5",
        'тест3 FAIL (исключение без имени: Поле не найдено "Валюта")',
        {"S": 10, "M": 0.0, "O": None, "P": 3.3, "Q": 4.4},
    )
    c = corpus(tmp_path, [rec], category="B")
    sec = audit._section_platform([c])
    assert "как FAIL и не попала в P — 1" in texts(sec)


def test_marker_without_platform_test(tmp_path):
    """Маркер в логе есть, а платформенных тестов ноль — классификатор его не увидел."""
    rec = (
        "B3",
        "id",
        "М",
        {
            "scores": {"S": 10, "M": 6.7, "O": 10, "P": 10.0, "Q": 9.2},
            "detail": {
                "S": {},
                "O": {"leg": "O-авто"},
                "M": {
                    "status": "ok",
                    "log": "тест3 FAIL (…)",
                    "platform_errors": ["Метод объекта не обнаружен"],
                    "platform_error_tests": 0,
                },
                "P": {"total": 3, "platform_error_tests": 0},
            },
        },
    )
    c = corpus(tmp_path, [rec], category="B")
    sec = audit._section_platform([c])
    assert "платформенных тестов ноль — 1" in texts(sec)


# ── инфраструктура ───────────────────────────────────────────────────────────


def test_infra_failure_found_by_reason_text(tmp_path):
    """Статуса в detail может не быть — инфраструктурный отказ опознаётся по причине."""
    rec = (
        "B1",
        "id",
        "М",
        {
            "scores": {"S": None, "M": None, "O": None, "P": None, "Q": None},
            "detail": {
                "S": {"reason": "исполнение не состоялось (no_result)"},
                "M": {
                    "reason": "исполнение не состоялось (no_result)",
                    "infra_detail": "result.txt не создан",
                },
                "O": {"leg": "O-исп-B"},
                "P": {},
            },
        },
    )
    c = corpus(tmp_path, [rec], category="B")
    sec = audit._section_infra([c])
    assert "по инфраструктуре — 1" in texts(sec)


def test_category_a_timeout_counted_as_model_fault(tmp_path):
    """Кат. A: таймаут исполнения даёт M=0, и вина не отделена."""
    rec = (
        "A1",
        "id",
        "М",
        {
            "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
            "detail": {
                "S": {},
                "M": {"executed": False, "errors": ["таймаут исполнения"]},
                "O": {"leg": "O-исп"},
            },
        },
    )
    c = corpus(tmp_path, [rec], category="A")
    sec = audit._section_infra([c])
    assert "таймаут исполнения засчитан как M=0" in texts(sec)
    assert "— 1" in texts(sec)


# ── задачи и Q ───────────────────────────────────────────────────────────────


def test_task_flagged_by_zero_meaning_share(tmp_path):
    """Задача, где почти все решения нулевые, уходит на ревизию."""
    zero = {"S": 10, "M": 0.0, "O": None, "P": 10.0, "Q": 6.7}
    good = {"S": 10, "M": 10.0, "O": 10, "P": 10.0, "Q": 10.0}
    pairs = [("B9", "id", f"М{i}", {"scores": zero}) for i in range(3)]
    pairs += [("B9", "id", "М4", {"scores": good})]
    pairs += [("B8", "id", f"Н{i}", {"scores": good}) for i in range(4)]
    c = corpus(tmp_path, pairs, category="B")
    sec = audit._section_tasks([c])
    assert "— 1" in texts(sec)
    assert any("B9" in line for line in sec["details"]["задачи на ревизию"])


def test_quality_lift_from_unmeasured_axis(tmp_path):
    """Выпадение оси O поднимает Q: отчёт показывает, насколько."""
    rec = (
        "T1",
        "id",
        "М",
        {
            "scores": {"S": 10, "M": 0.0, "O": None, "P": None, "Q": 5.0},
            "detail": {"O": {"leg": "O-исп", "note": "не исполнился"}},
        },
    )
    c = corpus(tmp_path, [rec], category="A")
    sec = audit._section_quality([c])
    assert "Q выше за счёт выпадения оси O — 1" in texts(sec)


# ── дрейф ────────────────────────────────────────────────────────────────────


def test_drift_reports_changed_and_vanished(tmp_path):
    """Сверка с базовой линией: что изменилось и что исчезло."""
    ep, ap = write_corpus(tmp_path, [("T1", "id", "М", {})])
    base = tmp_path / "base"
    base.mkdir()
    old = json.loads(ap.read_text(encoding="utf-8"))
    old["tasks"][0]["runs"][0]["scores"]["O"] = None  # было не измерено, стало 10
    old["tasks"].append(
        {
            "task_id": "T2",
            "model_id": "id",
            "model_name": "М",
            "runs": [{"run_index": 0, "scores": {"S": 10}, "detail": {}}],
        }
    )
    (base / ap.name).write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    c = audit.load_corpus("A", experiment=ep, auto=ap)
    sec = audit._section_drift([c], base)
    assert "изменившихся оценок — 1" in texts(sec)
    assert "исчезло — 1" in texts(sec)
    assert any("O None → 10" in line for line in sec["details"]["дрейф A"])


def test_run_audit_on_synthetic_corpus_is_clean(tmp_path, monkeypatch):
    """Здоровый корпус проходит аудит без нарушений."""
    ep, ap = write_corpus(tmp_path, [("T1", "id", "М", {})])
    monkeypatch.setattr(audit, "newest_experiments", lambda: {"A": ep})
    monkeypatch.setattr(audit, "newest_auto", lambda cat: ap)
    sections, ok = audit.run_audit(category="A")
    assert ok, [t for s in sections for st, t in s["items"] if st == "fail"]


@pytest.mark.parametrize("section", ["связка рулона и оценок", "условия прогона", "ось O"])
def test_markdown_report_contains_sections(tmp_path, monkeypatch, section):
    ep, ap = write_corpus(tmp_path, [("T1", "id", "М", {})])
    monkeypatch.setattr(audit, "newest_experiments", lambda: {"A": ep})
    monkeypatch.setattr(audit, "newest_auto", lambda cat: ap)
    sections, _ = audit.run_audit(category="A")
    assert f"## {section}" in audit.to_markdown(sections)


def test_compiler_crash_is_reported_as_candidate_fault(tmp_path):
    """Сегфолт компилятора на модуле — вина кандидата с кодом, а не «инфраструктура»."""
    rec = (
        "B3",
        "id",
        "М",
        {
            "response": "Функция Ф() КонецФункции",
            "scores": {"S": 0, "M": 0.0, "O": None, "P": 0.0, "Q": 0.0},
            "detail": {
                "S": {"compiler_exit": 139},
                "M": {"status": "candidate_error", "compiler_exit": 139, "entry_point": "Ф"},
                "O": {"leg": "O-авто"},
                "P": {},
            },
        },
    )
    c = corpus(tmp_path, [rec], category="B")
    sec = audit._section_infra([c])
    assert "роняет компилятор платформы — 1" in texts(sec)
    assert "по инфраструктуре — 0" in texts(sec)
