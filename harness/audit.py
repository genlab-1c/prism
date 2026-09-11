"""Аудит корпуса результатов (prism audit): инварианты поверх готовых оценок.

Чем отличается от prism check. Check проверяет ОПРЕДЕЛЕНИЕ бенчмарка: контракты метрики,
задания, эталоны. Audit проверяет его РЕЗУЛЬТАТЫ: связку рулона с оценками, согласованность
осей между собой, условия прогона и расхождение с базовой линией. Это разные вопросы, и
зелёный check ничего не говорит про здоровье корпуса: линейку мы проверяем вежливым кодом
эталонов, а мерим ею невежливый код моделей.

Аудит НИЧЕГО НЕ ПРАВИТ. Он читает results/ и печатает, где данные противоречат сами себе.
Решение, что с этим делать (пересчёт, регенерация, правка протокола), принимает человек.

Статусы пунктов: ok — инвариант держится; warn — расхождение, требующее взгляда; fail —
данные противоречивы и выводы по ним делать нельзя; skip — проверка неприменима.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from harness.loaders import load_error_taxonomy, load_protocol_l1
from harness.orchestrate import extract_code, newest_auto, newest_experiments

Item = tuple[str, str]
Section = dict  # {"title": str, "items": list[Item], "details": dict[str, list[str]]}

# Объявление функции или процедуры в начале строки — то же, чем детектирует точку входа
# харнесс (harness/execute/onec/runner.py:SUB_RE). Английские ключевые слова BSL принимает
# наравне с русскими, поэтому учитываем оба языка: иначе аудит не увидит объявления там,
# где его видит компилятор.
DECL_RE = re.compile(
    r"^\s*(?:Функция|Процедура|Function|Procedure)\s+([\wа-яА-ЯёЁ]+)\s*\(",
    re.MULTILINE | re.IGNORECASE,
)
EXEC_MARKER = "Ошибка при вызове метода контекста (Выполнить)"
# Инфраструктурный отказ кат. B: статуса в detail нет, остаётся только текст причины.
INFRA_REASON = "исполнение не состоялось"
FUNC_ONLY_RE = re.compile(
    r"^\s*(?:Функция|Function)\s+[\wа-яА-ЯёЁ]+\s*\(", re.MULTILINE | re.IGNORECASE
)
PROC_RE = re.compile(
    r"^\s*(?:Процедура|Procedure)\s+[\wа-яА-ЯёЁ]+\s*\(", re.MULTILINE | re.IGNORECASE
)
# Длина блока инструментированных хелперов в cand.operf.os: номера строк в нотах оси O
# кат. A сдвинуты на неё относительно кода модели (см. score/cost_model.HELPERS).
O_NOTE_LINE_RE = re.compile(r"Error in line:?\s*(\d+)")
M_ZERO_TASK_THRESHOLD = 0.55  # доля нулевой M по задаче, выше которой задача идёт на ревизию


# ── загрузка корпуса ──────────────────────────────────────────────────────────


def load_corpus(category: str, experiment: Path | None = None, auto: Path | None = None) -> dict:
    """Свести рулон генерации и файл оценок в плоский список записей.

    Ключ записи — (задача, ИМЯ модели, номер прогона). Имя, а не id: id привязан к каналу
    доступа и у части моделей менялся, поэтому одна модель встречается в корпусе под двумя id.
    """
    exp_path = experiment or newest_experiments().get(category)
    auto_path = auto or newest_auto(category)
    if exp_path is None or auto_path is None or not Path(exp_path).exists():
        return {
            "category": category,
            "records": [],
            "meta": {},
            "exp_path": exp_path,
            "auto_path": auto_path,
            "orphans": [],
            "dups": [],
            "unscored": [],
            "model_ids": {},
        }

    exp = json.loads(Path(exp_path).read_text(encoding="utf-8"))
    au = json.loads(Path(auto_path).read_text(encoding="utf-8"))

    gen: dict[tuple, dict] = {}
    gen_ids: dict[str, set[str]] = defaultdict(set)
    for tr in exp["task_results"]:
        gen_ids[tr["model_name"]].add(tr["model_id"])
        for r in tr["runs"]:
            gen[(tr["task_id"], tr["model_name"], r["run_index"])] = {"tr": tr, "r": r}

    # Одна пара (задача, модель, прогон) может встретиться в оценках дважды: след прошлого
    # скоринга под прежним id канала. Живая запись — та, чей хеш ответа совпадает с рулоном.
    by_key: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    for g in au.get("tasks", []):
        for r in g["runs"]:
            by_key[(g["task_id"], g["model_name"], r["run_index"])].append((g, r))

    records, orphans, dups = [], [], []
    seen = set()
    for key, entries in by_key.items():
        src = gen.get(key)
        if src is None:
            for g, r in entries:
                orphans.append(
                    {
                        "key": key,
                        "model_id": g.get("model_id"),
                        "hash": r.get("response_hash"),
                        "scores": r.get("scores", {}),
                    }
                )
            continue
        if len(entries) > 1:
            live = next(
                (
                    e
                    for e in entries
                    if (e[1].get("response_hash") or "") == (src["r"].get("response_hash") or "")
                ),
                entries[-1],
            )
            for entry in entries:
                if entry is live:
                    continue
                g, r = entry
                dups.append(
                    {
                        "key": key,
                        "model_id": g.get("model_id"),
                        "hash": r.get("response_hash"),
                        "scores": r.get("scores", {}),
                        "detail": r.get("detail", {}),
                    }
                )
            entries = [live]
        for g, r in entries:
            seen.add(key)
            gr = src["r"]
            records.append(
                {
                    "cat": category,
                    "task_id": g["task_id"],
                    "model_name": g["model_name"],
                    "model_id_auto": g.get("model_id"),
                    "model_id_gen": src["tr"]["model_id"],
                    "run_index": r["run_index"],
                    "scores": r.get("scores", {}),
                    "detail": r.get("detail", {}),
                    "hash_auto": r.get("response_hash") or "",
                    "hash_gen": gr.get("response_hash") or "",
                    "response": gr.get("response") or "",
                    "code": extract_code(gr.get("response") or ""),
                    "tokens_output": gr.get("tokens_output", 0),
                    "max_tokens": gr.get("max_tokens", 0),
                    "provenance": gr.get("provenance", ""),
                    "generated_at": gr.get("generated_at", ""),
                    "success": gr.get("success", True),
                    "error": gr.get("error"),
                }
            )

    return {
        "category": category,
        "records": records,
        "meta": {
            k: au.get(k) for k in ("protocol_version", "constitution_version", "edition", "runner")
        },
        "exp_path": Path(exp_path),
        "auto_path": Path(auto_path),
        "orphans": orphans,
        "dups": dups,
        "unscored": sorted(set(gen) - seen),
        "model_ids": {n: sorted(v) for n, v in gen_ids.items()},
    }


# ── вспомогательное ───────────────────────────────────────────────────────────


def _key(rec: dict) -> str:
    return f"{rec['task_id']} · {rec['model_name']}"


def _o_note(rec: dict) -> str:
    o = rec["detail"].get("O") or {}
    return (o.get("note") or o.get("reason") or "").strip()


def _subclass(text: str, rules: list[dict]) -> dict | None:
    for rule in rules:
        if any(m in text for m in rule["match"]):
            return rule
    return None


def _infra_failed(rec: dict) -> bool:
    """Прогон не состоялся по инфраструктуре: статус или текст причины говорят об этом."""
    m = rec["detail"].get("M") or {}
    return m.get("status") in ("no_result", "infra_error") or INFRA_REASON in (
        m.get("reason") or ""
    )


def _status(n: int, warn_above: int = 0) -> str:
    return "ok" if n == 0 else ("warn" if n <= warn_above else "fail")


# ── секция 1: связка рулона и оценок ─────────────────────────────────────────


def _section_linkage(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}

    orphans = [(c["category"], o) for c in corpora for o in c["orphans"]]
    items.append((_status(len(orphans)), f"сироты: оценки без пары в рулоне — {len(orphans)}"))
    if orphans:
        details["сироты"] = [
            f"{cat} {o['key'][0]} · {o['key'][1]} · прогон {o['key'][2]} · id={o['model_id']} · "
            f"хеш ответа {'отсутствует' if not o['hash'] else o['hash'][:12]} · {o['scores']}"
            for cat, o in orphans
        ]

    dups = [(c["category"], d) for c in corpora for d in c["dups"]]
    items.append(
        (
            _status(len(dups)),
            f"дубли: две оценки на одну генерацию (след прошлого скоринга) — {len(dups)}",
        )
    )
    if dups:
        details["дубли оценок"] = [
            f"{cat} {d['key'][0]} · {d['key'][1]} · прогон {d['key'][2]} · id={d['model_id']} · "
            f"хеш ответа {'отсутствует' if not d['hash'] else d['hash'][:12]} · {d['scores']} · "
            f"статус M={(d['detail'].get('M') or {}).get('status')}"
            for cat, d in dups
        ]

    unscored = [(c["category"], k) for c in corpora for k in c["unscored"]]
    items.append((_status(len(unscored)), f"генерации без оценки — {len(unscored)}"))
    if unscored:
        details["без оценки"] = [f"{cat} {k[0]} · {k[1]} · прогон {k[2]}" for cat, k in unscored]

    mism = [r for c in corpora for r in c["records"] if r["hash_auto"] != r["hash_gen"]]
    items.append(
        (_status(len(mism)), f"оценка посчитана по другому ответу (хеши разошлись) — {len(mism)}")
    )
    if mism:
        details["хеши разошлись"] = [
            f"{r['cat']} {_key(r)}: в оценке {r['hash_auto'][:12] or 'нет'}, "
            f"в рулоне {r['hash_gen'][:12] or 'нет'}"
            for r in mism
        ]

    split = {
        (c["category"], n): ids
        for c in corpora
        for n, ids in c["model_ids"].items()
        if len(ids) > 1
    }
    items.append(
        (
            "warn" if split else "ok",
            f"модели под несколькими id (ключ пересчёта — имя) — {len(split)}",
        )
    )
    if split:
        details["несколько id"] = [
            f"{cat} {n}: {', '.join(ids)}" for (cat, n), ids in sorted(split.items())
        ]

    proto = load_protocol_l1().version if hasattr(load_protocol_l1(), "version") else None
    stale = [c for c in corpora if proto and c["meta"].get("protocol_version") != proto]
    items.append(
        (
            "warn" if stale else "ok",
            "версия протокола в файлах оценок: "
            + ", ".join(f"{c['category']}={c['meta'].get('protocol_version')}" for c in corpora)
            + (f" (текущая {proto})" if proto else ""),
        )
    )

    legacy = [
        r
        for c in corpora
        for r in c["records"]
        if "O" in r["detail"] and "leg" not in (r["detail"].get("O") or {})
    ]
    gated_legacy = [
        r for c in corpora for r in c["records"] if (r["detail"].get("O") or {}).get("gated")
    ]
    items.append(
        (
            _status(len(legacy) + len(gated_legacy), warn_above=0),
            f"записи старой схемы оси O: без поля leg — {len(legacy)}, "
            f"с легаси-полем gated — {len(gated_legacy)}",
        )
    )
    if legacy or gated_legacy:
        by_task = Counter(f"{r['cat']} {r['task_id']}" for r in legacy + gated_legacy)
        details["старая схема O"] = [f"{k}: {v}" for k, v in sorted(by_task.items())]
    return {"title": "связка рулона и оценок", "items": items, "details": details}


# ── секция 2: условия прогона ────────────────────────────────────────────────


def _section_provenance(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    recs = [r for c in corpora for r in c["records"]]

    unknown = [r for r in recs if not r["max_tokens"]]
    items.append(
        (
            _status(len(unknown), warn_above=0),
            f"условие прогона неизвестно (нет max_tokens) — {len(unknown)} из {len(recs)}",
        )
    )
    if unknown:
        details["без условия"] = [f"{r['cat']} {_key(r)}" for r in unknown[:50]]

    caps = Counter(r["max_tokens"] for r in recs if r["max_tokens"])
    items.append(
        (
            "warn" if len(caps) > 1 else "ok",
            "потолок выхода по корпусу: "
            + ", ".join(f"{c} → {n} прогонов" for c, n in sorted(caps.items())),
        )
    )

    ceiling = [r for r in recs if r["max_tokens"] and r["tokens_output"] >= r["max_tokens"]]
    items.append(
        (
            _status(len(ceiling), warn_above=0),
            f"ответ упёрся в потолок (обрыв по длине) — {len(ceiling)}",
        )
    )
    if ceiling:
        details["упёрлись в потолок"] = [
            f"{r['cat']} {_key(r)}: выход {r['tokens_output']} при потолке {r['max_tokens']}, "
            f"{'ответ пуст' if not r['code'].strip() else 'код оборван'}, "
            f"S={r['scores'].get('S')} M={r['scores'].get('M')} Q={r['scores'].get('Q')}"
            for r in ceiling
        ]

    empty = [r for r in recs if r["success"] and not r["code"].strip()]
    items.append(
        (_status(len(empty), warn_above=0), f"пустой ответ при успешном вызове — {len(empty)}")
    )
    if empty:
        details["пустой ответ"] = [
            f"{r['cat']} {_key(r)}: выход {r['tokens_output']} токенов, S={r['scores'].get('S')}, "
            f"Q={r['scores'].get('Q')}"
            for r in empty
        ]
    return {"title": "условия прогона", "items": items, "details": details}


# ── секция 3: ответ без кода против оси S ────────────────────────────────────


def _section_no_code(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    recs = [r for c in corpora for r in c["records"]]

    nodecl = [r for r in recs if not DECL_RE.search(r["code"])]
    positive = [r for r in nodecl if (r["scores"].get("S") or 0) > 0]
    items.append(
        (
            _status(len(positive), warn_above=0),
            f"в ответе нет ни функции, ни процедуры, а балл S положительный — "
            f"{len(positive)} из {len(nodecl)}",
        )
    )
    if nodecl:
        dist = Counter(r["scores"].get("S") for r in nodecl)
        details["нет объявления: распределение S"] = [
            f"S={k}: {v}" for k, v in sorted(dist.items(), key=lambda kv: (kv[0] is None, kv[0]))
        ]
        details["нет объявления: записи"] = [
            f"{r['cat']} {_key(r)}: S={r['scores'].get('S')} M={r['scores'].get('M')} "
            f"P={r['scores'].get('P')} Q={r['scores'].get('Q')} · "
            f"{'пусто' if not r['code'].strip() else 'есть текст без объявления'}"
            for r in nodecl
        ]

    # Слепое пятно детектора: объявление в коде ЕСТЬ, а точку входа скорер не нашёл.
    # Смотрим по факту (detail.M.entry_point), а не своим регэкспом: иначе аудит мерит не то,
    # что сделал скорер, и разъезжается с ним при первой же правке детектора.
    blind = [
        r
        for r in recs
        if DECL_RE.search(r["code"])
        and not (r["detail"].get("M") or {}).get("entry_point")
        and not _infra_failed(r)  # прогон не состоялся → точки входа нет по другой причине
    ]
    items.append(
        (
            _status(len(blind), warn_above=0),
            f"объявление в коде есть, а точка входа не найдена — {len(blind)}",
        )
    )
    if blind:
        only_proc = "только процедура"
        details["точка входа не найдена при наличии объявления"] = [
            f"{r['cat']} {_key(r)}: "
            + (
                only_proc
                if PROC_RE.search(r["code"]) and not FUNC_ONLY_RE.search(r["code"])
                else "есть функция"
            )
            + f" · S={r['scores'].get('S')} M={r['scores'].get('M')} Q={r['scores'].get('Q')}"
            for r in blind
        ]

    # Кат. B: компилятор теперь запускается и при отсутствии точки входа, поэтому S=10 у
    # такой записи — честный вердикт «модуль собрался, звать нечего», а не ложное утверждение.
    # Проверяем обратное: модуль собрался чисто, функция в коде есть, а позвать её не смогли.
    fake = [
        r
        for r in recs
        if r["cat"] == "B"
        and (r["detail"].get("M") or {}).get("status") == "no_entry"
        and (r["scores"].get("S") or 0) >= 10
        and DECL_RE.search(r["code"])
    ]
    items.append(
        (
            _status(len(fake), warn_above=0),
            f"кат. B: модуль собрался чисто и объявление есть, а позвать нечего — {len(fake)}",
        )
    )
    if fake:
        details["S без компилятора"] = [
            f"B {_key(r)}: S={r['scores'].get('S')}, инструмент в detail — "
            f"«{(r['detail'].get('S') or {}).get('instrument', '')}»"
            for r in fake
        ]
    return {"title": "ответ без кода против оси S", "items": items, "details": details}


# ── секция 4: ось O ──────────────────────────────────────────────────────────


def _section_optimization(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    recs = [r for c in corpora for r in c["records"]]

    # Строгий признак вины обвязки: код ИСПОЛНИЛСЯ в оси M, но ось O сообщает «не исполнился».
    broke = []
    for r in recs:
        note = _o_note(r)
        m = r["scores"].get("M")
        if (
            r["scores"].get("O") is None
            and m is not None
            and m > 0
            and note.startswith(("не исполнился", "таймаут уже", "замер не состоялся"))
        ):
            broke.append(r)
    items.append(
        (
            _status(len(broke), warn_above=0),
            f"код исполнился в оси M, но замер O не состоялся — {len(broke)}",
        )
    )
    if broke:
        hard = [r for r in broke if (r["scores"].get("M") or 0) >= 5]
        details["O не состоялась при рабочем коде"] = [
            f"{r['cat']} {_key(r)}: M={r['scores'].get('M')} · {_o_note(r)[:110]}"
            for r in sorted(broke, key=lambda x: -(x["scores"].get("M") or 0))
        ]
        items.append(
            (
                _status(len(hard), warn_above=0),
                f"  из них при M ≥ 5 (решение верное, а оптимальность потеряна) — {len(hard)}",
            )
        )

    # Причины N/A: одна причина маскирует другую, поэтому считаем по приоритету записи.
    na = [r for r in recs if r["scores"].get("O") is None]
    reasons = Counter()
    for r in na:
        o = r["detail"].get("O") or {}
        if o.get("gated_by_m"):
            reasons["гейт по M < 5"] += 1
        elif o.get("gated"):
            reasons["легаси-гейт (старая схема)"] += 1
        else:
            note = _o_note(r)
            reasons[re.sub(r"\d+", "N", note).split(":")[0][:60] or "без причины"] += 1
    items.append(("warn" if na else "ok", f"ось O не измерена — {len(na)} из {len(recs)}"))
    details["причины неизмеренной O"] = [f"{k}: {v}" for k, v in reasons.most_common()]

    # Номера строк в нотах кат. A — это строки файла-харнесса, не кода модели.
    shifted = [r for r in recs if r["cat"] == "A" and O_NOTE_LINE_RE.search(_o_note(r))]
    items.append(
        (
            ("warn" if shifted else "ok"),
            f"кат. A: ноты O с номером строки файла-харнесса (не кода модели) — {len(shifted)}",
        )
    )
    return {"title": "ось O", "items": items, "details": details}


# ── секция 5: оси M и P ──────────────────────────────────────────────────────


def _section_platform(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    rules = load_error_taxonomy().get("platform_subclasses") or []
    recs = [r for c in corpora for r in c["records"] if r["cat"] == "B"]
    if not recs:
        return {
            "title": "оси M и P (платформа)",
            "items": [("skip", "категории B нет в корпусе")],
            "details": {},
        }

    # Подклассы общего маркера «(Выполнить)»: метаданные (ось P) против авторства запроса (ось M).
    by_axis, unknown_texts = Counter(), Counter()
    by_code = Counter()
    mixed = []
    for r in recs:
        log = (r["detail"].get("M") or {}).get("log") or ""
        if EXEC_MARKER not in log:
            continue
        axes = set()
        for piece in re.split(r"(?=тест\d+\s)", log):
            if EXEC_MARKER not in piece:
                continue
            tail = piece.split("(Выполнить)", 1)[1]
            rule = _subclass(tail, rules)
            if rule is None:
                unknown_texts[re.sub(r'"[^"]*"', '"…"', tail.strip())[:60]] += 1
                continue
            by_code[f"{rule['code']} · {rule['label']}"] += 1
            by_axis[rule["axis"]] += 1
            axes.add(rule["axis"])
        if axes == {"M"} and (r["scores"].get("P") or 0) < 10:
            mixed.append(r)

    items.append(
        (
            "warn" if by_axis.get("M") else "ok",
            f"под маркером «(Выполнить)» ошибок авторства запроса (по конституции ось M) — "
            f"{by_axis.get('M', 0)}, обращений к метаданным (ось P) — {by_axis.get('P', 0)}",
        )
    )
    details["подклассы маркера (Выполнить)"] = [f"{k}: {v}" for k, v in by_code.most_common()]
    if unknown_texts:
        details["не опознано подклассами"] = [f"{k}: {v}" for k, v in unknown_texts.most_common()]
    items.append(
        (
            _status(len(mixed), warn_above=0),
            f"балл P снижен, хотя все ошибки «(Выполнить)» — про текст запроса — {len(mixed)}",
        )
    )
    if mixed:
        details["P снижен за синтаксис запроса"] = [
            f"B {_key(r)}: P={r['scores'].get('P')} M={r['scores'].get('M')}" for r in mixed
        ]

    # Классификатор P считает только сегменты «тестN ИСКЛЮЧЕНИЕ». Если тест сам поймал
    # исключение и записал его как FAIL, платформенная ошибка не учтена.
    swallowed = []
    for r in recs:
        m = r["detail"].get("M") or {}
        log = m.get("log") or ""
        for piece in re.split(r"(?=тест\d+\s)", log):
            if re.match(r"тест\d+\s+FAIL", piece) and any(
                mk in piece
                for mk in (
                    "Поле не найдено",
                    "Метод объекта не обнаружен",
                    "Таблица не найдена",
                    EXEC_MARKER,
                )
            ):
                swallowed.append(r)
                break
    items.append(
        (
            _status(len(swallowed), warn_above=0),
            f"платформенная ошибка записана тестом как FAIL и не попала в P — {len(swallowed)}",
        )
    )
    if swallowed:
        details["FAIL с платформенной ошибкой"] = [
            f"B {_key(r)}: P={r['scores'].get('P')} · "
            f"{(r['detail'].get('P') or {}).get('platform_error_tests')} из "
            f"{(r['detail'].get('P') or {}).get('total')} тестов сочтены платформенными"
            for r in swallowed
        ]

    nomatch = [
        r
        for r in recs
        if (r["detail"].get("M") or {}).get("platform_errors")
        and not (r["detail"].get("M") or {}).get("platform_error_tests")
    ]
    items.append(
        (
            _status(len(nomatch), warn_above=0),
            f"маркер в логе есть, а платформенных тестов ноль — {len(nomatch)}",
        )
    )
    if nomatch:
        details["маркер без теста"] = [
            f"B {_key(r)}: P={r['scores'].get('P')} · маркеры "
            f"{(r['detail'].get('M') or {}).get('platform_errors')}"
            for r in nomatch
        ]
    return {"title": "оси M и P (платформа)", "items": items, "details": details}


# ── секция 6: инфраструктура ─────────────────────────────────────────────────


def _section_infra(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    recs = [r for c in corpora for r in c["records"]]

    # Статус в detail сохраняется не всегда, поэтому смотрим и текст причины.
    infra = [r for r in recs if _infra_failed(r)]
    items.append(
        (
            "warn" if infra else "ok",
            f"кат. B: прогон не состоялся по инфраструктуре — {len(infra)} "
            f"(в воронку отказов такие записи не попадают вовсе)",
        )
    )
    if infra:
        details["инфраструктура B"] = [
            f"B {_key(r)}: {(r['detail'].get('M') or {}).get('reason') or (r['detail'].get('M') or {}).get('status')} · "
            f"{(r['detail'].get('M') or {}).get('infra_detail', '')[:90]} · оси {r['scores']}"
            for r in infra
        ]

    # Граница вины: модуль кандидата роняет компилятор платформы (сегфолт /CheckModules).
    # Раньше это тонуло в «инфраструктуре»; теперь это вина кандидата с кодом завершения.
    crashed = [r for r in recs if (r["detail"].get("M") or {}).get("compiler_exit")]
    items.append(
        (
            "warn" if crashed else "ok",
            f"кат. B: модуль кандидата роняет компилятор платформы — {len(crashed)}",
        )
    )
    if crashed:
        details["компилятор упал на модуле"] = [
            f"B {_key(r)}: код {(r['detail'].get('M') or {}).get('compiler_exit')} · "
            f"S={r['scores'].get('S')} M={r['scores'].get('M')} P={r['scores'].get('P')}"
            for r in crashed
        ]

    # Категория A статуса не имеет: таймаут и сбой песочницы выглядят как дефект модели.
    timeouts = [
        r
        for r in recs
        if r["cat"] == "A"
        and any("таймаут" in e for e in ((r["detail"].get("M") or {}).get("errors") or []))
    ]
    items.append(
        (
            "warn" if timeouts else "ok",
            f"кат. A: таймаут исполнения засчитан как M=0 (статуса вины нет) — {len(timeouts)}",
        )
    )
    if timeouts:
        details["таймауты A"] = [f"A {_key(r)}: M={r['scores'].get('M')}" for r in timeouts]
    return {"title": "инфраструктура против вины модели", "items": items, "details": details}


# ── секция 7: задачи ─────────────────────────────────────────────────────────


def _section_tasks(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    flagged = []
    for c in corpora:
        total, zero, clean_zero = Counter(), Counter(), Counter()
        for r in c["records"]:
            total[r["task_id"]] += 1
            if r["scores"].get("M") == 0:
                zero[r["task_id"]] += 1
                if r["scores"].get("P") == 10:
                    clean_zero[r["task_id"]] += 1
        for task, n in sorted(total.items()):
            share = zero[task] / n if n else 0
            if share >= M_ZERO_TASK_THRESHOLD:
                flagged.append((c["category"], task, zero[task], n, share, clean_zero[task]))
    items.append(
        (
            "warn" if flagged else "ok",
            f"задачи с долей нулевой M выше {int(M_ZERO_TASK_THRESHOLD * 100)}% "
            f"(кандидаты на ревизию условия или тестов) — {len(flagged)}",
        )
    )
    if flagged:
        details["задачи на ревизию"] = [
            f"{cat} {task}: M=0 у {z} из {n} ({share:.0%}), из них с чистой платформой (P=10) — {cz}"
            for cat, task, z, n, share, cz in sorted(flagged, key=lambda x: -x[4])
        ]
    return {"title": "задачи", "items": items, "details": details}


# ── секция 8: влияние неизмеренных осей на Q ─────────────────────────────────


def _section_quality(corpora: list[dict]) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    for c in corpora:
        recs = c["records"]
        if not recs:
            continue
        lifted = []
        for r in recs:
            sc = r["scores"]
            if sc.get("O") is not None or sc.get("Q") is None:
                continue
            measured = [v for a, v in sc.items() if a != "Q" and v is not None]
            with_zero = (sum(measured) + 0) / (len(measured) + 1) if measured else None
            if with_zero is not None and sc["Q"] - with_zero > 0.01:
                lifted.append((r, sc["Q"], with_zero))
        share = len(lifted) / len(recs)
        items.append(
            (
                "warn" if lifted else "ok",
                f"{c['category']}: Q выше за счёт выпадения оси O — {len(lifted)} записей "
                f"({share:.0%}); средний подъём "
                f"{(sum(q - z for _, q, z in lifted) / len(lifted)):.2f} балла"
                if lifted
                else f"{c['category']}: выпадение оси O на Q не влияет",
            )
        )
        if lifted:
            top = sorted(lifted, key=lambda x: -(x[1] - x[2]))[:10]
            details[f"подъём Q, {c['category']}"] = [
                f"{_key(r)}: Q={q:.2f}, было бы {z:.2f} при O=0 (M={r['scores'].get('M')})"
                for r, q, z in top
            ]
    return {"title": "влияние неизмеренных осей на Q", "items": items, "details": details}


# ── секция 9: дрейф против базовой линии ─────────────────────────────────────


def _section_drift(corpora: list[dict], baseline: Path) -> Section:
    items: list[Item] = []
    details: dict[str, list[str]] = {}
    for c in corpora:
        name = Path(c["auto_path"]).name if c["auto_path"] else None
        base = baseline / name if name else None
        if base is None or not base.exists():
            items.append(("skip", f"{c['category']}: в базовой линии нет файла {name}"))
            continue
        old = json.loads(base.read_text(encoding="utf-8"))
        prev = {
            (g["task_id"], g["model_name"], r["run_index"]): r.get("scores", {})
            for g in old.get("tasks", [])
            for r in g["runs"]
        }
        now = {(r["task_id"], r["model_name"], r["run_index"]): r["scores"] for r in c["records"]}
        changed = []
        for k in sorted(set(prev) & set(now)):
            diff = {
                a: (prev[k].get(a), now[k].get(a))
                for a in ("S", "M", "O", "P", "Q")
                if prev[k].get(a) != now[k].get(a)
            }
            if diff:
                changed.append((k, diff))
        appeared, gone = sorted(set(now) - set(prev)), sorted(set(prev) - set(now))
        items.append(
            (
                ("ok" if not (changed or appeared or gone) else "warn"),
                f"{c['category']}: изменившихся оценок — {len(changed)}, новых записей — "
                f"{len(appeared)}, исчезло — {len(gone)}",
            )
        )
        if changed:
            details[f"дрейф {c['category']}"] = [
                f"{k[0]} · {k[1]} · прогон {k[2]}: "
                + ", ".join(f"{a} {o} → {n}" for a, (o, n) in d.items())
                for k, d in changed[:80]
            ]
        if gone:
            details[f"исчезло {c['category']}"] = [f"{k[0]} · {k[1]} · прогон {k[2]}" for k in gone]
    return {"title": "дрейф против базовой линии", "items": items, "details": details}


# ── точка входа ───────────────────────────────────────────────────────────────


def run_audit(
    category: str | None = None,
    experiment: Path | None = None,
    auto: Path | None = None,
    baseline: Path | None = None,
) -> tuple[list[Section], bool]:
    """Инварианты по корпусу. Возвращает (секции, ok); ok=False при хотя бы одном fail."""
    cats = [category] if category else ["A", "B"]
    corpora = [load_corpus(c, experiment=experiment, auto=auto) for c in cats]
    corpora = [c for c in corpora if c["records"] or c["orphans"]]
    if not corpora:
        return [
            {
                "title": "корпус",
                "items": [("fail", "не найдено ни одного прогона в results/")],
                "details": {},
            }
        ], False

    head = {
        "title": "корпус",
        "items": [
            (
                "ok",
                f"{c['category']}: прогонов {len(c['records'])}, "
                f"моделей {len({r['model_name'] for r in c['records']})}, "
                f"задач {len({r['task_id'] for r in c['records']})} · "
                f"{Path(c['auto_path']).name if c['auto_path'] else '—'}",
            )
            for c in corpora
        ],
        "details": {},
    }

    sections = [
        head,
        _section_linkage(corpora),
        _section_provenance(corpora),
        _section_no_code(corpora),
        _section_optimization(corpora),
        _section_platform(corpora),
        _section_infra(corpora),
        _section_tasks(corpora),
        _section_quality(corpora),
    ]
    if baseline:
        sections.append(_section_drift(corpora, Path(baseline)))
    ok = not any(st == "fail" for s in sections for st, _ in s["items"])
    return sections, ok


def to_markdown(sections: list[Section]) -> str:
    """Отчёт для чтения человеком: пункты плюс полные списки записей."""
    out = ["# Аудит корпуса результатов PRISM", ""]
    glyph = {"ok": "норма", "warn": "внимание", "fail": "нарушение", "skip": "пропуск"}
    for s in sections:
        out += [f"## {s['title']}", ""]
        for st, text in s["items"]:
            out.append(f"- **{glyph.get(st, st)}**: {text}")
        out.append("")
        for name, lines in (s.get("details") or {}).items():
            out += [f"### {name}", ""]
            out += [f"- {line}" for line in lines]
            out.append("")
    return "\n".join(out)
