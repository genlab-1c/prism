"""Тесты оркестратора генерации — офлайн, на сценарном адаптере (без сети/ключей).

Проверяем: категория B end-to-end (агент собрал контекст → код кандидата → запись
в схему результатов), категория A без контекста, и арифметику детерминизма.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.generate.hashing import compare_hashes, compute_hash, normalize_code
from harness.generate.run import GenerationRunner
from harness.generate.types import LLMResult, ToolCall


def _tc(call_id: str, tool: str, **args) -> ToolCall:
    return ToolCall(id=call_id, function={"name": tool, "arguments": json.dumps(args)})


def _res(content="", tool_calls=None, tokens=10):
    return LLMResult(success=True, content=content, tool_calls=tool_calls, tokens_total=tokens)


class ScriptedAdapter:
    name = "scripted"
    supports_seed = True
    supports_tools = True

    def __init__(self, script):
        self._script = list(script)

    def chat(self, model_id, messages, **kw) -> LLMResult:
        return self._script.pop(0)


CODE = "```bsl\nФункция ПолучитьОстатки() Экспорт\nКонецФункции\n```"


def test_determinism_math():
    h = compute_hash(CODE)
    assert compare_hashes([h, h, h]) == {"total_runs": 3, "unique_count": 1, "match_rate": 1.0,
                                         "most_common_hash": h, "most_common_count": 3}
    mixed = compare_hashes([h, h, "g"])
    assert mixed["unique_count"] == 2 and abs(mixed["match_rate"] - 2 / 3) < 1e-9
    # нормализация: обёртка markdown-блока и хвостовой текст не влияют на хеш кода
    assert compute_hash(CODE) == compute_hash(CODE + "\n\n")
    assert normalize_code(CODE).startswith("Функция ПолучитьОстатки")


def test_category_b_end_to_end(monkeypatch):
    # сценарий claude: агент (list → structure → finish) + один codegen-прогон
    script = [
        _res(tool_calls=[_tc("1", "list_objects")]),
        _res(tool_calls=[_tc("2", "get_object_structure", name="РегистрНакопления.ТоварыНаСкладах")]),
        _res(tool_calls=[_tc("3", "finish_research", summary="беру ТоварыНаСкладах")]),
        _res(content=CODE),
    ]
    runner = GenerationRunner(adapter_factory=lambda key, entry: ScriptedAdapter(script))
    exp = runner.run_experiment("B", model_keys=["claude"], task_ids=["B1"], write=False)

    assert exp.tasks_count == 1 and len(exp.task_results) == 1
    tr = exp.task_results[0]
    assert tr.context_loaded and tr.context_objects == ["РегистрНакопления.ТоварыНаСкладах"]
    assert len(tr.runs) == 1                          # claude: runs=1, без seed
    assert tr.runs[0].seed is None
    assert tr.runs[0].response == CODE and tr.runs[0].response_hash
    assert tr.determinism.total_runs == 1 and tr.determinism.match_rate == 1.0


def test_category_a_no_context():
    runner = GenerationRunner(adapter_factory=lambda key, entry: ScriptedAdapter([_res(content=CODE)]))
    exp = runner.run_experiment("A", model_keys=["claude"], task_ids=["A1"], write=False)
    tr = exp.task_results[0]
    assert tr.context_loaded is False and tr.context_objects == []
    assert tr.runs[0].response == CODE


def test_seeds_used_for_seed_capable_model():
    # gpt: supports_seed=true, seeds=[178] → seed уходит в прогон
    runner = GenerationRunner(adapter_factory=lambda key, entry: ScriptedAdapter([_res(content=CODE)]))
    exp = runner.run_experiment("A", model_keys=["gpt"], task_ids=["A1"], write=False)
    assert exp.task_results[0].runs[0].seed == 178


# ── потребление полей издания/модели (правило «нет мёртвых строк») ──────────────

def _entry(**caps):
    from harness.loaders import ModelAccess, ModelEntry
    return ModelEntry(id="m", name="M", vendor="v",
                      access=ModelAccess(adapter="openrouter"), capabilities=caps)


def test_context_mode_must_be_agentic():
    from harness.loaders import load_tasks
    runner = GenerationRunner(adapter_factory=lambda k, e: ScriptedAdapter([]))
    task = next(t for t in load_tasks(category="B"))
    with pytest.raises(NotImplementedError):
        runner._gather_context(task, _entry(supports_tools=True), ScriptedAdapter([]), "flat")


def test_supports_tools_gates_agentic_context():
    from harness.loaders import load_tasks
    runner = GenerationRunner(adapter_factory=lambda k, e: ScriptedAdapter([]))
    task = next(t for t in load_tasks(category="B"))
    # без поддержки инструментов навигация невозможна → контекст пустой, адаптер не зовётся
    ctx = runner._gather_context(task, _entry(supports_tools=False, context_window=1000),
                                 ScriptedAdapter([]), "agentic")
    assert ctx.success and ctx.objects_loaded == []


def test_cli_generate_parses():
    from harness.cli import build_parser
    args = build_parser().parse_args(["generate", "--category", "B", "--models", "claude"])
    assert args.command == "generate" and args.category == "B"
    assert args.edition == "core" and args.models == ["claude"]


# ── чекпойнт / resume / кап стоимости (write=True во временную папку) ──────────

class CountingAdapter:
    """Адаптер-счётчик: фиксирует число вызовов chat в общий список."""
    name = "counting"
    supports_seed = False
    supports_tools = False

    def __init__(self, counter):
        self._counter = counter

    def chat(self, model_id, messages, **kw):
        self._counter.append(model_id)
        return _res(content=CODE)


def test_checkpoint_writes_parts_and_final(tmp_path):
    runner = GenerationRunner(adapter_factory=lambda k, e: CountingAdapter([]),
                              results_dir=tmp_path)
    exp = runner.run_experiment("A", model_keys=["claude"], task_ids=["A1", "A2"])
    assert (tmp_path / f"{exp.experiment_name}.json").exists()         # финал собран
    parts = list((tmp_path / f"{exp.experiment_name}.parts").glob("*.json"))
    assert {p.stem for p in parts} == {"A1__claude", "A2__claude"}     # чекпойнт на пару


def test_resume_skips_completed_pairs(tmp_path):
    calls: list[str] = []
    runner = GenerationRunner(adapter_factory=lambda k, e: CountingAdapter(calls),
                              results_dir=tmp_path)
    exp = runner.run_experiment("A", model_keys=["claude"], task_ids=["A1", "A2"])
    assert len(calls) == 2                                             # обе пары сгенерены

    calls.clear()
    again = runner.run_experiment("A", model_keys=["claude"], task_ids=["A1", "A2"],
                                  resume=exp.experiment_name)
    assert calls == []                                                # всё готово → сети нет
    assert len(again.task_results) == 2                               # но результат полный


def test_max_cost_cap_skips_all(tmp_path):
    calls: list[str] = []
    runner = GenerationRunner(adapter_factory=lambda k, e: CountingAdapter(calls),
                              results_dir=tmp_path, max_cost=0.0)
    exp = runner.run_experiment("A", model_keys=["claude"], task_ids=["A1", "A2"])
    assert calls == [] and exp.task_results == []                     # кап=0 → ни одного вызова


def test_leaderboard_view_ranks_models(capsys):
    from harness.orchestrate import print_summary
    result = {"leaderboard_view": "quality", "tasks": [
        {"task_id": "B1", "model_id": "a", "model_name": "Alpha",
         "runs": [{"run_index": 0, "scores": {"S": 10, "M": 10, "O": 10, "P": 10, "Q": 10.0}, "detail": {}}]},
        {"task_id": "B1", "model_id": "b", "model_name": "Beta",
         "runs": [{"run_index": 0, "scores": {"S": 10, "M": 0, "O": 6, "P": 0, "Q": 4.0}, "detail": {}}]},
    ]}
    print_summary(result, Path("/nonexistent.json"))
    out = capsys.readouterr().out
    assert "Лидерборд" in out
    assert out.index("Alpha") < out.index("Beta")          # Alpha (Q̄=10) выше Beta (Q̄=4)
