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
    q_formula: str                   # mean_of_applicable
    q_primary_result: str            # vector
    thresholds: dict[str, int]       # high / acceptable / low
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
    bound: float | None = None                        # граница сравнения (нет у хвостовой строки)
    exclusive: bool = False                           # строгое сравнение (< / >)
    is_else: bool = Field(False, alias="else")        # хвост «во всех прочих случаях»


class Scoring(BaseModel):
    """Единая таблица балла оси: сигнал → балл. Заменяет прежние bands+thresholds."""
    model_config = ConfigDict(extra="allow")          # unit/floor_note/recall_rule — справочные

    direction: str                                    # lower_is_better | higher_is_better
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
        return self.table[-1].score                   # подстраховка, если нет else-строки


class L1Axis(BaseModel):
    """Блок оси в metrics/smop_l1_auto.yaml: таблица балла + параметры инструмента."""
    model_config = ConfigDict(extra="allow")          # instrument/signal/measures — справочные

    scoring: Scoring | None = None
    pre_check: dict | None = None                     # эскейп в 0 минуя таблицу (S, P)
    cluster_gap: int | None = None                    # S: соседние ParseError ≤N строк = одна причина
    compile_blocker_codes: list[str] | None = None    # S: не-ParseError диагностики «не скомпилируется»
    white_list: dict[str, float] | None = None        # O: код диагностики BSL LS → вес
    applies_to: list[str] | None = None               # только у P


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


def load_protocol_l1(root: Path = PRISM) -> ProtocolL1:
    doc = _read(root / "metrics" / "smop_l1_auto.yaml")
    return ProtocolL1(axes=doc["axes"], version=doc["meta"]["version"])


# ── задачи ───────────────────────────────────────────────────────────────────

class TaskTests(BaseModel):
    """tests.yaml задачи: скрытые кейсы оси M."""

    entry_point_patterns: list[str] = Field(default_factory=list)
    tests: list[dict]                # {args: [...], expected: ...}


class Task(BaseModel):
    """Одна задача: tasks/<категория>/<id>/.

    Категория A: task.yaml (entry_point, signature) + tests.yaml + canonical.bsl —
    исполняется в OneScript. Категория B: task.yaml (entry_point_patterns,
    expected_objects) + config_spec.yaml + fixtures.yaml + tests.bsl + canonical.bsl —
    исполняется против синтетической базы 1С (harness/execute/onec).
    """

    id: str
    name: str
    category: str                    # "A" | "B"
    difficulty: str
    prompt: str
    dir: Path
    entry_point: str | None = None           # A: имя функции эталона
    signature: str | None = None             # A: точная сигнатура
    entry_point_patterns: list[str] = Field(default_factory=list)   # B: детекция функции
    expected_objects: list[str] = Field(default_factory=list)       # B: сид оси P
    tests: TaskTests | None = None           # A: скрытые кейсы (tests.yaml)
    canonical: Path | None = None    # эталон, если есть
    m_testing: str | None = None     # пометка вроде pending_harness

    @property
    def testable(self) -> bool:
        """Есть ли у задачи скрытые тесты (ось M исполнима).

        A — кейсы tests.yaml; B — полный комплект исполнения (спека базы,
        фикстуры, проверки tests.bsl).
        """
        if self.category == "B":
            return all((self.dir / f).exists()
                       for f in ("config_spec.yaml", "fixtures.yaml", "tests.bsl"))
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
        canonical_path = task_dir / "canonical.bsl"
        tasks.append(Task(
            **doc,
            dir=task_dir,
            tests=_read(tests_path) if tests_path.exists() else None,
            canonical=canonical_path if canonical_path.exists() else None,
        ))
    return tasks


# ── издание и генерация ──────────────────────────────────────────────────────

class Edition(BaseModel):
    """editions/<имя>.yaml — конфиг-профиль прогона."""

    name: str
    mode: str                        # single-shot | agentic
    context: str                     # none | mcp | ab
    scorers: list[str]               # оси, которые издание хочет считать
    leaderboard_view: str


def load_edition(name: str, root: Path = PRISM) -> Edition:
    return Edition(**_read(root / "editions" / f"{name}.yaml"))


class ModelAccess(BaseModel):
    """Канал доступа к модели (адаптер харнесса)."""

    adapter: str                     # openrouter | openai_compat | gigachat | …
    endpoint: str | None = None      # для openai_compat (Ollama/vLLM)


class ModelEntry(BaseModel):
    """Запись каталога generation/models.yaml."""

    id: str
    name: str
    vendor: str
    access: ModelAccess
    capabilities: dict


class Generation(BaseModel):
    """generation/: каталог моделей + числовые параметры + system-промпты."""

    models: dict[str, ModelEntry]
    params: dict                     # defaults из params.yaml
    prompts: dict[str, str]          # категория → system-промпт


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
