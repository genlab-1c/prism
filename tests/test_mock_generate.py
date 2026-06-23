"""Сухой прогон генерации (prism generate --mock) — офлайн, без сети и ключей."""

from __future__ import annotations

from harness.generate.adapters.mock import MockAdapter
from harness.generate.mock import MOCK_ID, build_mock_runner
from harness.generate.types import ChatMessage


def test_mock_adapter_returns_mapped_response_else_stub():
    adapter = MockAdapter({"условие A": "```bsl\nЭТАЛОН\n```"}, stub="ЗАГЛУШКА")
    hit = adapter.chat("mock/echo", [ChatMessage.user("условие A")])
    miss = adapter.chat("mock/echo", [ChatMessage.user("неизвестный промпт")])
    assert hit.success and "ЭТАЛОН" in hit.content
    assert miss.content == "ЗАГЛУШКА"
    assert hit.tokens_total > 0  # токены проставлены (грубо), стоимость считается отдельно


def test_mock_canonical_run_uses_canonical_per_task_offline():
    """Весь конвейер A проходит офлайн; ответ каждой пары — эталон именно её задачи."""
    runner = build_mock_runner("canonical", verbose=False)
    exp = runner.run_experiment("A", write=False)  # write=False — без записи в results/

    assert exp.tasks_count > 0
    assert exp.models_used == ["mock (эталон)"]
    assert exp.total_cost == 0.0
    for tr in exp.task_results:
        assert tr.model_id == MOCK_ID
        assert tr.runs and tr.runs[0].success
        assert tr.runs[0].response.startswith("```bsl")


def test_mock_stub_run_returns_stub_for_all():
    runner = build_mock_runner("stub", verbose=False)
    exp = runner.run_experiment("A", write=False)
    assert exp.task_results
    for tr in exp.task_results:
        assert "не реализовано" in tr.runs[0].response
