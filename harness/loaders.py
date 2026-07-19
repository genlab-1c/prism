"""
Загрузчики данных бенчмарка: YAML-контракты → Pydantic-модели.

Скореры берут банды из metrics/smop_l1_auto.yaml, раннер — оси из конституции
и издания, задачи — из tasks/<категория>/<id>/. Здесь нет ни одного порога.

Pydantic валидирует структуру YAML при загрузке: битый контракт падает сразу
с понятной ошибкой, а не глубоко в скорере.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PRISM = Path(__file__).resolve().parents[1]


# ── метрика: конституция ─────────────────────────────────────────────────────


class AxisSpec(BaseModel):
    """Блок одной оси в metrics/smop.yaml."""

    model_config = ConfigDict(extra="allow")

    name: str
    name_en: str
    applies_to: list[str]


class Constitution(BaseModel):
    """metrics/smop.yaml — определения осей, шкала, правило Q."""

    valid_scores: list[int]
    axes: dict[str, AxisSpec]
    q_formula: str  # mean_of_applicable
    q_primary_result: str  # vector
    thresholds: dict[str, int]  # high / acceptable / low
    version: str

    def applicable_axes(self, category: str) -> list[str]:
        """Оси, применимые к категории задачи (по applies_to конституции)."""
        return [a for a, spec in self.axes.items() if category in spec.applies_to]


def load_constitution(root: Path = PRISM) -> Constitution:
    doc = _read(root / "metrics" / "smop.yaml")
    return Constitution(
        valid_scores=doc["scale"]["valid_scores"],
        axes=doc["smop"],
        q_formula=doc["quality_score"]["formula"],
        q_primary_result=doc["quality_score"]["primary_result"],
        thresholds=doc["quality_thresholds"],
        version=doc["meta"]["version"],
    )


# ── метрика: протокол L1 ─────────────────────────────────────────────────────


class ScoringRule(BaseModel):
    """Строка таблицы scoring.table: порог → балл (см. шапку smop_l1_auto.yaml)."""

    model_config = ConfigDict(populate_by_name=True)

    score: int
    bound: float | None = None  # граница сравнения (нет у хвостовой строки)
    exclusive: bool = False  # строгое сравнение (< / >)
    is_else: bool = Field(False, alias="else")  # хвост «во всех прочих случаях»


class Scoring(BaseModel):
    """Таблица балла оси: сигнал → балл (единственный источник порогов для оси)."""

    model_config = ConfigDict(extra="allow")  # unit/floor_note/recall_rule — справочные

    direction: str  # lower_is_better | higher_is_better
    table: list[ScoringRule]

    def score_for(self, signal: float) -> int:
        """Балл по сигналу: строки сверху вниз, первый подходящий порог."""
        higher = self.direction == "higher_is_better"
        for rule in self.table:
            if rule.is_else:
                return rule.score
            if higher:
                hit = signal > rule.bound if rule.exclusive else signal >= rule.bound
            else:
                hit = signal < rule.bound if rule.exclusive else signal <= rule.bound
            if hit:
                return rule.score
        return self.table[-1].score  # подстраховка, если нет else-строки


class L1Axis(BaseModel):
    """Блок оси в metrics/smop_l1_auto.yaml: таблица балла + параметры инструмента."""

    model_config = ConfigDict(extra="allow")  # instrument/signal/measures — справочные

    scoring: Scoring | None = None
    exec_scoring: Scoring | None = (
        None  # O: исполнительная нога (категория A): отклонение роста от оптимума → балл
    )
    b_exec_scoring: Scoring | None = (
        None  # O: исполнительная нога (категория B): рост обращений к данным с ростом базы
    )
    pre_check: dict | None = None  # сразу 0 в обход таблицы баллов (оси S, P)
    cluster_gap: int | None = None  # S: соседние ParseError ≤N строк = одна причина
    compile_blocker_codes: list[str] | None = (
        None  # S: не-ParseError диагностики «не скомпилируется»
    )
    white_list: dict[str, float] | None = None  # O: код диагностики BSL LS → вес
    applies_to: list[str] | None = None  # только у P


class ProtocolL1(BaseModel):
    """metrics/smop_l1_auto.yaml — как машина выводит балл."""

    axes: dict[str, L1Axis]
    version: str

    def scoring(self, axis: str) -> Scoring:
        s = self.axes[axis].scoring
        assert s, f"у оси {axis} нет блока scoring в протоколе L1"
        return s

    def reachable(self, axis: str) -> list[int]:
        """Достижимые баллы = score из таблицы (+ 0, если у оси есть pre_check)."""
        a = self.axes[axis]
        scores = {r.score for r in a.scoring.table}
        if a.pre_check:
            scores.add(0)
        return sorted(scores)

    def o_weights(self) -> dict[str, float]:
        wl = self.axes["O"].white_list
        assert wl, "у оси O в протоколе L1 должен быть white_list"
        return wl

    def o_exec_scoring(self) -> Scoring:
        s = self.axes["O"].exec_scoring
        assert s, "у оси O в протоколе L1 нет блока exec_scoring (исполнительная нога)"
        return s

    def o_b_exec_scoring(self) -> Scoring:
        s = self.axes["O"].b_exec_scoring
        assert s, "у оси O в протоколе L1 нет блока b_exec_scoring (исполнительная нога кат. B)"
        return s


def load_protocol_l1(root: Path = PRISM) -> ProtocolL1:
    doc = _read(root / "metrics" / "smop_l1_auto.yaml")
    return ProtocolL1(axes=doc["axes"], version=doc["meta"]["version"])


# ── задачи ───────────────────────────────────────────────────────────────────


class TaskTests(BaseModel):
    """tests.yaml задачи: скрытые кейсы оси M."""

    entry_point_patterns: list[str] = Field(default_factory=list)
    tests: list[dict]  # {args: [...], expected: ...}


class TaskPerf(BaseModel):
    """perf.yaml: данные исполнительной оценки O.

    Общее: sizes — лесенка размеров входа; p_opt — оптимальный показатель роста задачи
    (балл O — по ОТКЛОНЕНИЮ роста кандидата от p_opt); call — замерочный вызов кандидата.
    Категория A: gen — BSL, строит вход размера {n} (call с {entry}).
    Категория B: grow — спека роста БАЗЫ (harness/execute/onec/perf_run.scale_fixtures),
    count — метрика роста обращений к СУБД (sdbl | register); call c {{ENTRY}}.
    """

    model_config = ConfigDict(extra="forbid")

    p_opt: float
    sizes: list[int]
    call: str
    gen: str | None = None  # A: BSL строит вход размера {n}
    grow: dict | None = None  # B: спека роста базы (композиция блоков)
    count: str = "sdbl"  # B: метрика роста (sdbl | register)


class Task(BaseModel):
    """Одна задача: tasks/<категория>/<id>/.

    Категория A: task.yaml (entry_point, signature) + tests.yaml + canonical.bsl —
    исполняется в OneScript. Категория B: task.yaml (entry_point_patterns,
    expected_objects) + config_spec.yaml + fixtures.yaml + tests.bsl + canonical.bsl —
    исполняется против синтетической базы 1С (harness/execute/onec).
    """

    id: str
    name: str
    category: str  # "A" | "B"
    difficulty: str
    prompt: str
    dir: Path
    entry_point: str | None = None  # A: имя функции эталона
    signature: str | None = None  # A: точная сигнатура
    entry_point_patterns: list[str] = Field(default_factory=list)  # B: детекция функции
    expected_objects: list[str] = Field(default_factory=list)  # B: сид оси P
    tests: TaskTests | None = None  # A: скрытые кейсы (tests.yaml)
    perf: TaskPerf | None = None  # A: данные исполнительной оценки O (perf.yaml)
    canonical: Path | None = None  # эталон, если есть
    perf_baseline: Path | None = None  # A: медленный якорь оси O (perf_baseline.bsl), если есть
    m_testing: str | None = None  # пометка вроде pending_harness
    tags: dict[str, list[str]] = Field(default_factory=dict)  # измерение → теги (срезы анализа)

    @property
    def testable(self) -> bool:
        """Есть ли у задачи скрытые тесты (ось M исполнима).

        A — кейсы tests.yaml; B — полный комплект исполнения (спека базы,
        фикстуры, проверки tests.bsl).
        """
        if self.category == "B":
            return all(
                (self.dir / f).exists() for f in ("config_spec.yaml", "fixtures.yaml", "tests.bsl")
            )
        return self.tests is not None and bool(self.tests.tests)


def load_tasks(root: Path = PRISM, category: str | None = None) -> list[Task]:
    """Все задачи из tasks/category_*/<id>/, отсортированы по id."""
    tasks = []
    for task_yaml in sorted((root / "tasks").glob("category_*/*/task.yaml")):
        doc = _read(task_yaml)
        if category and doc["category"] != category:
            continue
        task_dir = task_yaml.parent
        tests_path = task_dir / "tests.yaml"
        perf_path = task_dir / "perf.yaml"
        canonical_path = task_dir / "canonical.bsl"
        baseline_path = task_dir / "perf_baseline.bsl"
        tasks.append(
            Task(
                **doc,
                dir=task_dir,
                tests=_read(tests_path) if tests_path.exists() else None,
                perf=_read(perf_path) if perf_path.exists() else None,
                canonical=canonical_path if canonical_path.exists() else None,
                perf_baseline=baseline_path if baseline_path.exists() else None,
            )
        )
    return tasks


# ── словарь тегов (контролируемый, для срезов анализа) ───────────────────────


class TagDimension(BaseModel):
    """Измерение тегов: значения + мультизначность + применимость к категории."""

    multi: bool = True
    values: list[str]
    applies_to: list[str] | None = None  # None = ко всем категориям


class TagsVocab(BaseModel):
    """tasks/tags.yaml — закрытый словарь тегов по измерениям."""

    dimensions: dict[str, TagDimension]
    version: str

    def validate_task_tags(self, tags: dict[str, list[str]], category: str) -> list[str]:
        """Ошибки тегов задачи против словаря (пусто = валидно)."""
        errors = []
        for dim, values in (tags or {}).items():
            spec = self.dimensions.get(dim)
            if spec is None:
                errors.append(f"неизвестное измерение тегов {dim!r}")
                continue
            if spec.applies_to and category not in spec.applies_to:
                errors.append(f"измерение {dim!r} неприменимо к категории {category}")
            if not spec.multi and len(values) > 1:
                errors.append(f"измерение {dim!r} одно­значно, а задано {values}")
            for v in values:
                if v not in spec.values:
                    errors.append(f"{dim}: неизвестный тег {v!r}")
        return errors


def load_tags_vocab(root: Path = PRISM) -> TagsVocab:
    doc = _read(root / "tasks" / "tags.yaml")
    return TagsVocab(dimensions=doc["dimensions"], version=doc["meta"]["version"])


def load_error_taxonomy(root: Path = PRISM) -> dict:
    """metrics/error_taxonomy.yaml — словарь «текст ошибки → код» для воронки отказа."""
    return _read(root / "metrics" / "error_taxonomy.yaml")


# ── издание и генерация ──────────────────────────────────────────────────────


class Edition(BaseModel):
    """editions/<имя>.yaml — конфиг-профиль прогона."""

    name: str
    mode: str  # single-shot | agentic
    context: str  # none | mcp | ab
    scorers: list[str]  # оси, которые издание хочет считать
    leaderboard_view: str


def load_edition(name: str, root: Path = PRISM) -> Edition:
    return Edition(**_read(root / "editions" / f"{name}.yaml"))


class ModelAccess(BaseModel):
    """Канал доступа к модели (адаптер харнесса)."""

    adapter: str  # openrouter | openai_compat | gigachat | …
    endpoint: str | None = None  # для openai_compat (Ollama/vLLM)
    reasoning_effort: str | None = (
        None  # Responses API: "none" — отключить reasoning (Qwen3.6 и др.)
    )


class ModelEntry(BaseModel):
    """Запись каталога generation/models.yaml."""

    id: str
    name: str
    vendor: str
    weights: str | None = None  # open | proprietary; полноту каталога гейтит prism check
    released: str | None = None  # дата релиза модели, YYYY-MM-DD (или YYYY-MM, если известен месяц)
    access: ModelAccess
    capabilities: dict


class Generation(BaseModel):
    """generation/: каталог моделей + числовые параметры + system-промпты."""

    models: dict[str, ModelEntry]
    params: dict  # defaults из params.yaml
    prompts: dict[str, str]  # категория → system-промпт


def load_generation(root: Path = PRISM) -> Generation:
    return Generation(
        models=_read(root / "generation" / "models.yaml")["models"],
        params=_read(root / "generation" / "params.yaml")["defaults"],
        prompts=_read(root / "generation" / "prompts.yaml")["system"],
    )


# ── внутреннее ───────────────────────────────────────────────────────────────


def _read(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
