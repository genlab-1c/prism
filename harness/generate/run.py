"""Оркестратор генерации: издание × модели → код кандидатов → results/experiment_*.json.

Поток на пару (задача, модель):
  кат. B — агент собирает контекст метаданных (AgenticContextLoader над синтетическим
           спеком) → контекст дописывается к системному промпту;
  N прогонов с seed (по capabilities модели) → хеш ответа → анализ детерминизма;
  сборка ExperimentResult в схеме скорера → запись JSON.

Адаптеры инъектируются (adapter_factory) — в тестах подставляется сценарный адаптер,
поэтому весь конвейер проверяется офлайн, без сети и ключей. Реальный прогон —
adapter_factory по умолчанию (registry.build_adapter), нужны ключи в окружении.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import yaml

from harness.loaders import PRISM, ModelEntry, Task, load_generation, load_tasks

from .adapters.base import Adapter
from .context import AgenticContextLoader, SpecMetadataProvider
from .hashing import compare_hashes, compute_hash
from .results import DeterminismResult, ExperimentResult, RunResult, TaskResult
from .types import ChatMessage

AdapterFactory = Callable[[str, ModelEntry], Adapter]


def _default_factory(model_key: str, entry: ModelEntry) -> Adapter:
    from .adapters.registry import build_adapter
    return build_adapter(entry.access.adapter, endpoint=entry.access.endpoint)


class GenerationRunner:
    """Прогон генерации по конфигу prism (generation/* + tasks/)."""

    def __init__(self, adapter_factory: AdapterFactory = _default_factory,
                 results_dir: Path | None = None, distractors: dict | None = None):
        self.adapter_factory = adapter_factory
        self.results_dir = results_dir or (PRISM / "results")
        self.distractors = distractors          # {n_registers,...} | None — раздувание схемы (стог)
        gen = load_generation()
        self.models = gen.models
        self.params = gen.params
        self.prompts = gen.prompts               # {категория: system-текст}

    # ── публичный API ────────────────────────────────────────────────────────
    def run_experiment(self, category: str, model_keys: list[str] | None = None,
                       task_ids: list[str] | None = None, write: bool = True) -> ExperimentResult:
        tasks = [t for t in load_tasks(category=category)
                 if task_ids is None or t.id in task_ids]
        keys = model_keys or list(self.models)
        runs_per = max((self._runs_for(k) for k in keys), default=0)

        exp = ExperimentResult(
            experiment_name=f"experiment_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            category=category, timestamp=datetime.now().isoformat(),
            models_used=[self.models[k].name for k in keys if k in self.models],
            tasks_count=len(tasks), runs_per_task=runs_per)

        for task in tasks:
            for key in keys:
                entry = self.models.get(key)
                if entry is None:
                    continue
                exp.task_results.append(self._run_pair(task, key, entry, category))

        exp.calculate_totals()
        if write:
            self._save(exp)
        return exp

    # ── одна пара (задача, модель) ─────────────────────────────────────────────
    def _run_pair(self, task: Task, key: str, entry: ModelEntry, category: str) -> TaskResult:
        adapter = self.adapter_factory(key, entry)
        tr = TaskResult(task_id=task.id, task_name=task.name,
                        model_id=entry.id, model_name=entry.name)

        # контекст метаданных (агентный режим) — только для B
        context_text = ""
        if category == "B":
            ctx = self._load_context(task, entry, adapter)
            context_text = ctx.context_text
            tr.context_loaded = bool(ctx.objects_loaded)
            tr.context_objects = ctx.objects_loaded

        messages = self._build_messages(category, task.prompt, context_text)

        seeds = self._seeds_for(key, entry)
        mp = self.params.get("model_params", {}).get(key, {})
        temperature = mp.get("temperature", 0.0)
        max_tokens = self.params.get("max_tokens", 4096)

        hashes: list[str] = []
        for i, seed in enumerate(seeds):
            out = adapter.chat(entry.id, messages, temperature=temperature,
                               max_tokens=max_tokens, seed=seed)
            run = RunResult(run_index=i, seed=seed, temperature=temperature,
                            success=out.success, response=out.content,
                            tokens_input=out.tokens_input, tokens_output=out.tokens_output,
                            tokens_total=out.tokens_total, elapsed_time=out.elapsed,
                            error=out.error)
            if out.success and out.content:
                run.response_hash = compute_hash(out.content)
                hashes.append(run.response_hash)
            tr.runs.append(run)

        if hashes:
            stats = compare_hashes(hashes)
            tr.determinism = DeterminismResult(unique_responses=stats["unique_count"],
                                               hashes=hashes, **{k: stats[k] for k in
                                               ("total_runs", "match_rate", "most_common_hash",
                                                "most_common_count")})
        tr.calculate_aggregates()
        return tr

    # ── вспомогательное ────────────────────────────────────────────────────────
    def _load_context(self, task: Task, entry: ModelEntry, adapter: Adapter):
        spec = yaml.safe_load((task.dir / "config_spec.yaml").read_text(encoding="utf-8"))
        if self.distractors:
            from harness.synthconfig import add_distractors
            spec = add_distractors(spec, **self.distractors)
        loader = AgenticContextLoader(adapter, SpecMetadataProvider(spec), entry.id)
        return loader.load(task.prompt)

    def _build_messages(self, category: str, task_prompt: str, context_text: str) -> list[ChatMessage]:
        system = self.prompts.get(category, "")
        if context_text:
            system = f"{system}\n\n# Метаданные конфигурации:\n{context_text}"
        return [ChatMessage.system(system), ChatMessage.user(task_prompt)]

    def _seeds_for(self, key: str, entry: ModelEntry) -> list[int | None]:
        """Список seed по прогонам: seeds из params, если модель их поддерживает; иначе [None]*runs."""
        mp = self.params.get("model_params", {}).get(key, {})
        supports = entry.capabilities.get("supports_seed", False)
        seeds = mp.get("seeds")
        if seeds and supports:
            return list(seeds)
        runs = mp.get("runs") or (len(seeds) if seeds else 1)
        return [None] * runs

    def _runs_for(self, key: str) -> int:
        mp = self.params.get("model_params", {}).get(key, {})
        return len(mp["seeds"]) if mp.get("seeds") else (mp.get("runs") or 1)

    def _save(self, exp: ExperimentResult) -> Path:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / f"{exp.experiment_name}.json"
        path.write_text(json.dumps(exp.model_dump(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path
