"""Предполётные проверки готовности (prism doctor / prism ping).

doctor — быстрый (секунды, без прогонов в 1С) ответ «всё ли у меня есть»: окружение,
инструменты осей, какие ключи моделей заданы. Сетевых вызовов не делает.

ping — наоборот, живой минимальный запрос к каждой модели: проверяет, что ключ рабочий
и канал отвечает. Тратит немного токенов (по одному короткому запросу на модель).

Логика отделена от печати: doctor_sections()/ping_models() возвращают данные (удобно
тестировать), render_*() печатают их в консоль.
"""

from __future__ import annotations

import platform
import shutil

from harness.check import Item, Section, _check_instruments
from harness.execute.onec import runner as onec
from harness.execute.runner import get_runner
from harness.generate.adapters.registry import (
    ADAPTER_REQUIRED_KEYS,
    AdapterConfigError,
    build_adapter,
)
from harness.generate.types import ChatMessage
from harness.loaders import load_generation
from harness.settings import credentials_env
from harness.ui import STATUS_STYLE, console

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("prism-bench")
except Exception:  # noqa: BLE001 — запуск из исходников
    _VERSION = "dev"

# Короткий запрос пинга: минимум токенов, детерминированно.
_PING_PROMPT = "Ответь одним символом: 1"


# ── doctor ────────────────────────────────────────────────────────────────────


def _env_section() -> Section:
    items: list[Item] = [
        ("ok", f"Python {platform.python_version()} · PRISM {_VERSION}"),
    ]
    uv = shutil.which("uv")
    items.append(("ok", f"uv: {uv}") if uv else ("warn", "uv не найден в PATH — см. make setup"))
    return {"title": "Окружение", "items": items}


def _keys_section() -> tuple[Section, bool]:
    """Какие ключи моделей заданы (по каналам каталога). Возвращает (секция, есть_ли_рабочий_канал)."""
    env = credentials_env()
    gen = load_generation()
    by_adapter: dict[str, list[str]] = {}
    for key, m in gen.models.items():
        by_adapter.setdefault(m.access.adapter, []).append(key)

    items: list[Item] = []
    any_ready = False
    for adapter in sorted(by_adapter):
        models = ", ".join(sorted(by_adapter[adapter]))
        required = ADAPTER_REQUIRED_KEYS.get(adapter, [])
        if not required:
            items.append(("ok", f"{adapter}: ключ не требуется (локальный endpoint) — {models}"))
            any_ready = True
            continue
        missing = [k for k in required if k not in env]
        if not missing:
            items.append(("ok", f"{adapter}: {', '.join(required)} заданы → {models}"))
            any_ready = True
        else:
            items.append(("warn", f"{adapter}: нет {', '.join(missing)} → пропустятся: {models}"))
    if not items:
        items.append(("warn", "в каталоге нет моделей"))
    return {"title": "Ключи моделей (.env)", "items": items}, any_ready


def doctor_sections() -> tuple[list[Section], dict]:
    """Секции отчёта doctor + словарь готовности (для вердикта и тестов)."""
    keys_section, gen_ready = _keys_section()
    sections = [_env_section(), _check_instruments(), keys_section]
    verdict = {
        "generation": gen_ready,
        "score_a": get_runner().available(),
        "score_b": onec.available(),
    }
    return sections, verdict


def render_sections(sections: list[Section]) -> None:
    for s in sections:
        console.print(f"\n{s['title']}", style="bold", markup=False, highlight=False)
        for status, text in s["items"]:
            glyph, style = STATUS_STYLE.get(status, ("?", "dim"))
            console.print(f"  {glyph} {text}", style=style, markup=False, highlight=False)


def render_doctor(sections: list[Section], verdict: dict) -> None:
    render_sections(sections)

    def mark(ok: bool) -> str:
        return "[green]✓[/green]" if ok else "[red]✗[/red]"

    console.print(
        f"\nГотов к: генерации {mark(verdict['generation'])} · "
        f"оценке A {mark(verdict['score_a'])} · оценке B {mark(verdict['score_b'])}",
        highlight=False,
    )


# ── ping ──────────────────────────────────────────────────────────────────────


def ping_models(model_keys: list[str] | None = None) -> list[dict]:
    """Живой минимальный запрос к каждой модели. Тратит немного токенов.

    Возвращает список {key, name, adapter, status, detail}:
      ok   — модель ответила (detail — время);
      fail — ключ есть, но запрос не прошёл (detail — ошибка);
      skip — нет ключа канала (запрос не делался).
    """
    env = credentials_env()
    gen = load_generation()
    keys = [k for k in (model_keys or list(gen.models)) if k in gen.models]
    results: list[dict] = []
    for key in keys:
        m = gen.models[key]
        adapter_name = m.access.adapter
        base = {"key": key, "name": m.name, "adapter": adapter_name}
        missing = [k for k in ADAPTER_REQUIRED_KEYS.get(adapter_name, []) if k not in env]
        if missing:
            results.append({**base, "status": "skip", "detail": f"нет {', '.join(missing)}"})
            continue
        try:
            adapter = build_adapter(
                adapter_name,
                endpoint=m.access.endpoint,
                reasoning_effort=m.access.reasoning_effort,
            )
            out = adapter.chat(
                m.id, [ChatMessage.user(_PING_PROMPT)], temperature=0.0, max_tokens=8
            )
        except AdapterConfigError as e:
            results.append({**base, "status": "skip", "detail": str(e)})
            continue
        except Exception as e:  # noqa: BLE001 — любой сбой канала → fail, не падение команды
            results.append({**base, "status": "fail", "detail": str(e)[:120]})
            continue
        if out.success:
            results.append({**base, "status": "ok", "detail": f"{out.elapsed:.1f}s"})
        else:
            results.append({**base, "status": "fail", "detail": (out.error or "ошибка")[:120]})
    return results


def render_ping(results: list[dict]) -> None:
    console.print(
        "проверка связи с моделями (минимальный запрос — тратит немного токенов)\n",
        style="bold",
        highlight=False,
    )
    for r in results:
        glyph, style = STATUS_STYLE.get(r["status"], ("?", "dim"))
        line = f"  {glyph} {r['key']:<14}{r['adapter']:<16}{r['detail']}"
        console.print(line, style=style, markup=False, highlight=False)
    n_ok = sum(r["status"] == "ok" for r in results)
    n_fail = sum(r["status"] == "fail" for r in results)
    n_skip = sum(r["status"] == "skip" for r in results)
    console.print(
        f"\nитог: {n_ok} ✓ · {n_fail} ✗ · {n_skip} пропуск", style="bold", highlight=False
    )
