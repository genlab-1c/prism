"""Оркестратор генерации: издание × модели → код кандидатов → results/experiment_*.json.

Поток на пару (задача, модель):
  кат. B — агент собирает контекст метаданных (AgenticContextLoader над синтетическим
           спеком) → контекст дописывается к системному промпту;
  N прогонов с seed (по capabilities модели) → хеш ответа → анализ детерминизма;
  сборка ExperimentResult в схеме скорера → запись JSON.

Операционная надёжность (слой поверх метрики, на баллы не влияет):
  • чекпойнт на пару — каждый готовый TaskResult сразу пишется в <exp>.parts/, финал
    собирается из частей. Падение на 60/100 → готовое не потеряно;
  • resume — повторный запуск с тем же именем дозапускает только недостающие/упавшие пары;
  • ретрай — транзиентный сбой сети повторяется с бэкоффом (retry.with_retry);
  • параллелизм — независимые пары идут пулом потоков (I/O-bound), кап на провайдера;
  • бюджет — живой счётчик стоимости с мягким капом (--max-cost) и предполётной оценкой.

Адаптеры инъектируются (adapter_factory) — в тестах подставляется сценарный адаптер,
поэтому весь конвейер проверяется офлайн, без сети и ключей. Реальный прогон —
adapter_factory по умолчанию (registry.build_adapter), нужны ключи в окружении.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import yaml
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from harness.loaders import PRISM, ModelEntry, Task, load_edition, load_generation, load_tasks
from harness.ui import console

from .adapters.base import Adapter
from .budget import CostMeter, estimate_cost
from .context import AgenticContextLoader, ContextResult, SpecMetadataProvider
from .hashing import compare_hashes, compute_hash
from .pricing import PriceTable, load_pricing
from .results import DeterminismResult, ExperimentResult, RunResult, TaskResult
from .retry import with_retry
from .types import ChatMessage

AdapterFactory = Callable[[str, ModelEntry], Adapter]


def _default_factory(model_key: str, entry: ModelEntry) -> Adapter:
    from .adapters.registry import build_adapter

    return build_adapter(entry.access.adapter, endpoint=entry.access.endpoint)


class GenerationRunner:
    """Прогон генерации по конфигу prism (generation/* + tasks/)."""

    def __init__(
        self,
        adapter_factory: AdapterFactory = _default_factory,
        results_dir: Path | None = None,
        distractors: dict | None = None,
        concurrency: int | None = None,
        max_cost: float | None = None,
        retries: int = 3,
        retry_base_delay: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        verbose: bool = False,
        pricing: PriceTable | None = None,
        models: dict | None = None,
        params: dict | None = None,
    ):
        self.adapter_factory = adapter_factory
        self.results_dir = results_dir or (PRISM / "results")
        self.distractors = (
            distractors  # {n_registers,...} | None — добавить шумовые объекты в схему
        )
        self.max_cost = max_cost
        self.retries = retries
        self.retry_base_delay = retry_base_delay
        self._sleep = sleep
        self.verbose = verbose
        self.pricing = pricing or load_pricing()
        gen = load_generation()  # каталог/параметры можно переопределить (тесты)
        self.models = models if models is not None else gen.models
        self.params = params if params is not None else gen.params
        self.prompts = gen.prompts  # {категория: system-текст}
        self.concurrency = concurrency or int(self.params.get("concurrency", 4))
        # лимиты параллелизма на канал доступа (GigaChat/Yandex строже облака)
        self._provider_limits: dict[str, int] = dict(self.params.get("provider_concurrency", {}))
        self._sems: dict[str, threading.Semaphore] = {
            name: threading.Semaphore(n) for name, n in self._provider_limits.items()
        }
        self._warned_prices: set[str] = set()
        self._lock = threading.Lock()
        self._progress_sink: Progress | None = (
            None  # живой прогресс-бар (терминал) — сток _progress
        )

    # ── публичный API ────────────────────────────────────────────────────────
    def run_experiment(
        self,
        category: str,
        model_keys: list[str] | None = None,
        task_ids: list[str] | None = None,
        edition_name: str = "core",
        write: bool = True,
        resume: str | None = None,
    ) -> ExperimentResult:
        edition = load_edition(edition_name)
        if edition.mode != "single-shot":  # издание.mode — одна кодогенерация на прогон
            raise NotImplementedError(
                f"издание {edition_name}: mode={edition.mode!r} не реализован "
                f"(поддержан single-shot)"
            )
        tasks = [t for t in load_tasks(category=category) if task_ids is None or t.id in task_ids]
        keys = [k for k in (model_keys or list(self.models)) if k in self.models]
        runs_per = max((self._runs_for(k) for k in keys), default=0)

        exp_name = resume or f"experiment_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        exp = ExperimentResult(
            experiment_name=exp_name,
            category=category,
            timestamp=datetime.now().isoformat(),
            models_used=[self.models[k].name for k in keys],
            tasks_count=len(tasks),
            runs_per_task=runs_per,
        )

        parts_dir = self.results_dir / f"{exp_name}.parts"
        pairs = [(task, key) for task in tasks for key in keys]  # детерминированный порядок

        # resume: уже завершённые пары пропускаем, их стоимость учитываем в счётчике
        done: dict[tuple[str, str], TaskResult] = {}
        meter = CostMeter(self.max_cost)
        if resume:
            for task, key in pairs:
                tr = self._load_part(parts_dir, task.id, key)
                if tr is not None and tr.runs and all(r.success for r in tr.runs):
                    done[(task.id, key)] = tr
                    meter.add(tr.total_cost)
            if done:
                self._progress(
                    f"resume {exp_name}: готово {len(done)}/{len(pairs)} пар, "
                    f"добираем {len(pairs) - len(done)}"
                )

        pending = [(t, k) for (t, k) in pairs if (t.id, k) not in done]
        if write:
            parts_dir.mkdir(parents=True, exist_ok=True)

        def work(task: Task, key: str) -> tuple[tuple[str, str], TaskResult | None]:
            if meter.exceeded():  # кап исчерпан → новые пары не запускаем
                self._progress(f"· пропуск {task.id}×{key}: бюджет ${self.max_cost} исчерпан")
                return (task.id, key), None
            sem = self._sems.get(self.models[key].access.adapter)
            if sem:
                sem.acquire()
            try:
                tr = self._run_pair(task, key, self.models[key], category, edition.context)
            except Exception as e:  # noqa: BLE001 — пара упала жёстко: не роняем прогон
                self._progress(f"✗ {task.id}×{key}: {e} — пара останется для resume")
                return (task.id, key), None
            finally:
                if sem:
                    sem.release()
            meter.add(tr.total_cost)
            if not any(r.success for r in tr.runs):  # ни один прогон не удался (сеть/доступ) →
                err = tr.runs[0].error if tr.runs else "нет прогонов"  # как исключение: не пишем,
                self._progress(
                    f"⚠ {task.id}×{key}: генерация не удалась ({err}) — пара останется для resume"
                )
                return (task.id, key), None  # resume повторит; в эксперимент не попадёт
            if write:
                self._write_part(parts_dir, task.id, key, tr)
            self._progress(f"✓ {task.id}×{key}  (${meter.spent:.4f} всего)")
            return (task.id, key), tr

        results: dict[tuple[str, str], TaskResult] = dict(done)
        if pending:
            # Живой прогресс-бар по парам — только в интерактивном терминале при verbose;
            # на не-tty (пайп/CI/перехват pytest) бар не поднимается, сообщения идут print.
            bar = self.verbose and console.is_terminal
            progress = (
                Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    MofNCompleteColumn(),
                    TimeElapsedColumn(),
                    console=console,
                )
                if bar
                else nullcontext()
            )
            with progress:
                bar_task = progress.add_task("генерация пар", total=len(pending)) if bar else None
                self._progress_sink = progress if bar else None
                try:
                    with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
                        for pkey, tr in pool.map(lambda p: work(*p), pending):
                            if tr is not None:
                                results[pkey] = tr
                            if bar:
                                progress.advance(bar_task)
                finally:
                    self._progress_sink = None

        # сборка в исходном (детерминированном) порядке пар
        exp.task_results = [results[(t.id, k)] for (t, k) in pairs if (t.id, k) in results]
        exp.calculate_totals()
        if write:
            self._save(exp)
        return exp

    def estimate(
        self, category: str, model_keys: list[str] | None = None, task_ids: list[str] | None = None
    ) -> dict:
        """Предполётная (грубая верхняя) оценка стоимости без вызовов сети."""
        tasks = [t for t in load_tasks(category=category) if task_ids is None or t.id in task_ids]
        keys = [k for k in (model_keys or list(self.models)) if k in self.models]
        max_tokens = int(self.params.get("max_tokens", 4096))
        pairs = [(self.models[k].id, self._runs_for(k)) for _ in tasks for k in keys]
        est = estimate_cost(self.pricing, pairs, max_tokens)
        est["pairs"] = len(pairs)
        return est

    # ── одна пара (задача, модель) ─────────────────────────────────────────────
    def _run_pair(
        self, task: Task, key: str, entry: ModelEntry, category: str, context_mode: str
    ) -> TaskResult:
        adapter = self.adapter_factory(key, entry)
        tr = TaskResult(
            task_id=task.id, task_name=task.name, model_id=entry.id, model_name=entry.name
        )

        # доставка метаданных для B задаётся изданием (edition.context)
        context_text = ""
        if category == "B":
            ctx = self._gather_context(task, entry, adapter, context_mode)
            context_text = ctx.context_text
            tr.context_loaded = bool(ctx.objects_loaded)
            tr.context_objects = ctx.objects_loaded
            _, _, ctx_cost = self._cost(entry.id, ctx.tokens_input, ctx.tokens_output)
            tr.context_analysis_cost = ctx_cost

        messages = self._build_messages(category, task.prompt, context_text)

        seeds = self._seeds_for(key, entry)
        mp = self.params.get("model_params", {}).get(key, {})
        temperature = mp.get("temperature", 0.0)
        max_tokens = self.params.get("max_tokens", 4096)

        hashes: list[str] = []
        for i, seed in enumerate(seeds):
            out = with_retry(
                lambda seed=seed: adapter.chat(
                    entry.id, messages, temperature=temperature, max_tokens=max_tokens, seed=seed
                ),
                retries=self.retries,
                base_delay=self.retry_base_delay,
                sleep=self._sleep,
                on_retry=lambda n, err, d: self._progress(
                    f"  ↻ {task.id}×{key} попытка {n}: {err} — пауза {d:.0f}с"
                ),
            )
            ci, co, ct = self._cost(entry.id, out.tokens_input, out.tokens_output)
            run = RunResult(
                run_index=i,
                seed=seed,
                temperature=temperature,
                success=out.success,
                response=out.content,
                tokens_input=out.tokens_input,
                tokens_output=out.tokens_output,
                tokens_total=out.tokens_total,
                elapsed_time=out.elapsed,
                cost_input=ci,
                cost_output=co,
                cost_total=ct,
                error=out.error,
            )
            if out.success and out.content:
                run.response_hash = compute_hash(out.content)
                hashes.append(run.response_hash)
            tr.runs.append(run)

        if hashes:
            stats = compare_hashes(hashes)
            tr.determinism = DeterminismResult(
                unique_responses=stats["unique_count"],
                hashes=hashes,
                **{
                    k: stats[k]
                    for k in ("total_runs", "match_rate", "most_common_hash", "most_common_count")
                },
            )
        tr.calculate_aggregates()
        return tr

    # ── вспомогательное ────────────────────────────────────────────────────────
    def _cost(self, model_id: str, tokens_in: int, tokens_out: int) -> tuple[float, float, float]:
        if not self.pricing.known(model_id):
            with self._lock:
                if model_id not in self._warned_prices:
                    self._warned_prices.add(model_id)
                    self._progress(
                        f"⚠ нет цены для {model_id} в pricing.yaml — стоимость "
                        f"по этой модели не учтена"
                    )
        return self.pricing.cost(model_id, tokens_in, tokens_out)

    def _gather_context(self, task: Task, entry: ModelEntry, adapter: Adapter, context_mode: str):
        if context_mode != "agentic":  # издание core — agentic; прочие режимы — план
            raise NotImplementedError(f"context={context_mode!r} не реализован (поддержан agentic)")
        # без поддержки инструментов навигация по метаданным невозможна → без контекста
        if not entry.capabilities.get("supports_tools"):
            return ContextResult(success=True)
        spec = yaml.safe_load((task.dir / "config_spec.yaml").read_text(encoding="utf-8"))
        if self.distractors:
            from harness.synthconfig import add_distractors

            spec = add_distractors(spec, **self.distractors)
        budget = int(
            entry.capabilities.get("context_window", 15000)
        )  # бюджет контекста — из окна модели
        loader = AgenticContextLoader(
            adapter, SpecMetadataProvider(spec), entry.id, max_context_chars=budget
        )
        return loader.load(task.prompt)

    def _build_messages(
        self, category: str, task_prompt: str, context_text: str
    ) -> list[ChatMessage]:
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

    # ── чекпойнт/сборка ────────────────────────────────────────────────────────
    @staticmethod
    def _part_path(parts_dir: Path, task_id: str, key: str) -> Path:
        return parts_dir / f"{task_id}__{key}.json"

    def _write_part(self, parts_dir: Path, task_id: str, key: str, tr: TaskResult) -> None:
        path = self._part_path(parts_dir, task_id, key)
        tmp = path.with_suffix(".json.tmp")  # атомарная запись: tmp → rename
        tmp.write_text(json.dumps(tr.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _load_part(self, parts_dir: Path, task_id: str, key: str) -> TaskResult | None:
        path = self._part_path(parts_dir, task_id, key)
        if not path.exists():
            return None
        try:
            return TaskResult(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — битый чекпойнт → перезапустим пару
            return None

    def _save(self, exp: ExperimentResult) -> Path:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        path = self.results_dir / f"{exp.experiment_name}.json"
        path.write_text(
            json.dumps(exp.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def _progress(self, msg: str) -> None:
        if not self.verbose:
            return
        sink = self._progress_sink
        if sink is not None:  # печатаем НАД живым баром, не ломая его
            sink.console.print(msg, markup=False, highlight=False)
        else:
            print(msg, flush=True)
