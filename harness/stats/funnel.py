"""Воронка отказа: где и как умирает прогон, а не сколько он набрал баллов.

Лидерборд баллов отвечает «насколько хорошо». Воронка отвечает на другое:
 • ГДЕ модель ломается — на каком этапе конвейера (разбор → запуск → верно);
 • КАК ломается — типизированная причина (см. metrics/error_taxonomy.yaml).

Три общих ворота (обе категории заполняют все три; токенчейн разный, но смысл один):
 1. разбор  — модуль прошёл статический разбор/компиляцию инструмента
              (кат. A: BSL Language Server; кат. B: 1С /CheckModules).
 2. запуск  — дошёл до выполнения тестов: нашлась точка входа, нет падения в исполнении.
 3. верно   — все скрытые тесты пройдены.

Ключевой принцип честности — АТРИБУЦИЯ К КОРНЮ, без двойного счёта. Один корень даёт
каскад: не скомпилировался → автоматически 0 по M/P/O. Поэтому причина засчитывается
ТАМ, ГДЕ ПРОГОН ВПЕРВЫЕ УМЕР, а не на каждой оси отдельно. Колонка воронки — это
кумулятивная доля доживших до этапа, а не независимые проценты.

Вход — структура auto_l1 (как пишет orchestrate) + словарь ошибок (loaders).
"""

from __future__ import annotations

from collections import Counter

STAGES = ("разбор", "запуск", "верно")

# Чем закончилась попытка — человеческое слово вместо «дожил до этапа N». Делим по
# ПРИРОДЕ провала, не по этапу: «ошибка выполнения» собирает все падения (не запустилось,
# исключение, обращение к несуществующим объектам базы), «неверный ответ» — когда код
# отработал, но результат не тот. Сумма по группам = все измеренные прогоны (100%).
# Порядок — от лучшего к худшему.
BUCKETS = ("решено", "неверный ответ", "ошибка выполнения", "не компилируется")


def bucket_of(outcome: dict) -> str:
    """Чем кончилась попытка: решено / неверный ответ / ошибка выполнения / не компилируется."""
    died = outcome["died"]
    if died is None:
        return "решено"
    if died == "разбор":
        return "не компилируется"
    if died == "запуск":
        return "ошибка выполнения"
    # died == "верно": код отработал, но тесты не прошли — результат не тот ИЛИ упало
    return "неверный ответ" if outcome["code"] == "M.WRONG" else "ошибка выполнения"


def _category(task_id: str) -> str:
    """Категория задачи по её id (A1, B10 …) — для выбора набора ворот."""
    return (task_id or "?")[:1].upper()


def _classify(text: str, taxonomy: dict) -> tuple[str, str] | None:
    """Первое правило словаря, чей фрагмент встретился в тексте → (код, человеч. имя)."""
    if not text:
        return None
    for rule in taxonomy.get("rules", []):
        if any(frag in text for frag in rule.get("match", [])):
            return rule["code"], rule["label"]
    return None


def _default(taxonomy: dict, key: str) -> tuple[str, str]:
    d = taxonomy["defaults"][key]
    return d["code"], d["label"]


def run_outcome(run: dict, taxonomy: dict) -> dict | None:
    """Судьба одного прогона: до какого этапа дожил и (если умер) почему.

    Возврат: {"reached": int 0..3 — пройдено ворот, "died": stage|None,
              "code": str|None, "label": str|None}. None — прогон не измерен
      (инфра-сбой/нет оси), как и в остальной агрегации он в воронку не идёт.
    """
    cat = _category(run.get("task_id", ""))
    det = run.get("detail") or {}
    s = det.get("S") or {}
    m = det.get("M") or {}
    scores = run.get("scores") or {}

    # не измерено: нет синтаксиса (инфра упала до анализа) — исключаем из воронки
    if scores.get("S") is None and not s:
        return None

    # ── ворота 1: разбор / компиляция ────────────────────────────────────────
    if cat == "B":
        # в 1С /CheckModules разбор и компиляция слиты: candidate_error ⟺ не собрался
        compiled = m.get("status") != "candidate_error"
        compile_text = "; ".join(m.get("compile_errors") or []) or m.get("log") or ""
    else:
        # кат. A: статический разбор BSL LS (root_causes) отдельно от OneScript
        compiled = s.get("root_causes", 0) == 0
        compile_text = "; ".join(s.get("errors") or [])
    if not compiled:
        code, label = _classify(compile_text, taxonomy) or _default(taxonomy, "parse")
        return {"reached": 0, "died": "разбор", "code": code, "label": label}

    # ── ворота 2: запуск (точка входа найдена, исполнение без падения) ────────
    if cat == "B":
        ran = m.get("status") == "ok"  # ok = собралось и тесты выполнились
        run_text = m.get("log") or ""
    else:
        ran = bool(m.get("executed")) and m.get("entry_point") is not None
        run_text = "; ".join(m.get("errors") or [])
    if not ran:
        no_entry = (cat == "B" and m.get("status") == "no_entry") or (
            cat == "A" and m.get("entry_point") is None
        )
        if no_entry:
            code, label = _default(taxonomy, "noentry")
        else:
            code, label = _classify(run_text, taxonomy) or _default(taxonomy, "run")
        return {"reached": 1, "died": "запуск", "code": code, "label": label}

    # ── ворота 3: верно (все тесты пройдены) ─────────────────────────────────
    total = m.get("total") or 0
    passed = m.get("passed") or 0
    if total == 0 or passed < total:
        # платформенная причина (кат. B) ловится структурой, а не текстом
        if m.get("platform_errors") or m.get("platform_error_tests"):
            code, label = _default(taxonomy, "meta")
        else:
            text = m.get("log") or "; ".join(m.get("errors") or [])
            hit = _classify(text, taxonomy)
            # нет исключения в тексте → код отработал и тихо дал неверный ответ
            code, label = hit or _default(taxonomy, "wrong")
        return {"reached": 2, "died": "верно", "code": code, "label": label}

    return {"reached": 3, "died": None, "code": None, "label": None}


def model_funnel(runs: list[dict], taxonomy: dict) -> dict | None:
    """Воронка одной модели по всем её прогонам.

    Возврат:
      "n"       — измеренных прогонов;
      "buckets" — {исход: число прогонов} в порядке BUCKETS (сумма = n) — это и есть отсев;
      "solved"  — доля «решено» (0..1), ключ сортировки;
      "cause"   — (человеч. причина, число) самой частой поломки среди НЕ решённых.
    reach (кумулятивная доля доживших) оставлен для тех, кому нужна классическая воронка.
    """
    outcomes = [o for o in (run_outcome(r, taxonomy) for r in runs) if o is not None]
    n = len(outcomes)
    if not n:
        return None
    buckets = {b: 0 for b in BUCKETS}
    for o in outcomes:
        buckets[bucket_of(o)] += 1
    reach = {STAGES[i]: sum(o["reached"] > i for o in outcomes) / n for i in range(3)}
    causes = Counter(o["label"] for o in outcomes if o["died"] is not None)
    top = causes.most_common(1)
    cause = (top[0][0], top[0][1]) if top else None
    return {
        "n": n,
        "buckets": buckets,
        "solved": buckets["решено"] / n,
        "reach": reach,
        "cause": cause,
    }


def funnel(result: dict, taxonomy: dict) -> list[tuple[str, dict]]:
    """Воронки всех моделей результата, ранжир по доле дошедших до «верно» (убыв.).

    result — структура auto_l1; группы {model_id, model_name, runs} как в orchestrate.
    Прогоны помечаются task_id, чтобы run_outcome выбрал ворота по категории.
    """
    by_model: dict[tuple, list] = {}
    for t in result.get("tasks", []):
        key = (t["model_id"], t["model_name"])
        for r in t["runs"]:
            by_model.setdefault(key, []).append({**r, "task_id": t["task_id"]})

    rows: list[tuple[str, dict]] = []
    for (_mid, mname), runs in by_model.items():
        f = model_funnel(runs, taxonomy)
        if f is not None:
            rows.append((mname, f))
    rows.sort(key=lambda kv: kv[1]["solved"], reverse=True)
    return rows
