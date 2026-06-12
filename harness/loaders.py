"""Загрузчики данных бенчмарка: YAML-контракты → Pydantic-модели.

Принцип (docs/architecture.md): код читает данные, данные не живут в коде.
Скореры берут банды из metrics/smop_l1_auto.yaml, раннер — оси из конституции
и издания, задачи — из tasks/<категория>/<id>/. Здесь нет ни одного порога.

Pydantic валидирует структуру YAML при загрузке: битый контракт падает сразу
с понятной ошибкой, а не глубоко в скорере.

Самопроверка (грузит всё и печатает сводку):  python3 -m harness.loaders
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PRISM = Path(__file__).resolve().parents[1]          # корень репозитория


# ── метрика: конституция ─────────────────────────────────────────────────────

class AxisSpec(BaseModel):
    """Блок одной оси в metrics/smop.yaml."""
    model_config = ConfigDict(extra="allow")          # measures/excludes/… — справочные

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

class L1Axis(BaseModel):
    """Блок оси в metrics/smop_l1_auto.yaml (банды, достижимые значения, веса)."""
    model_config = ConfigDict(extra="allow")          # instrument/signal/… — справочные

    reachable_scores: list[int]
    bands: dict[int, str]
    weights: dict[str, float] | None = None           # только у O
    applies_to: list[str] | None = None               # только у P


class ProtocolL1(BaseModel):
    """metrics/smop_l1_auto.yaml — как машина выводит балл."""

    axes: dict[str, L1Axis]
    version: str

    def bands(self, axis: str) -> dict[int, str]:
        return self.axes[axis].bands

    def reachable(self, axis: str) -> list[int]:
        return self.axes[axis].reachable_scores

    def o_weights(self) -> dict[str, float]:
        weights = self.axes["O"].weights
        assert weights, "у оси O в протоколе L1 должен быть белый список weights"
        return weights


def load_protocol_l1(root: Path = PRISM) -> ProtocolL1:
    doc = _read(root / "metrics" / "smop_l1_auto.yaml")
    return ProtocolL1(axes=doc["axes"], version=doc["meta"]["version"])


# ── задачи ───────────────────────────────────────────────────────────────────

class TaskTests(BaseModel):
    """tests.yaml задачи: скрытые кейсы оси M."""

    entry_point_patterns: list[str] = Field(default_factory=list)
    tests: list[dict]                # {args: [...], expected: ...}


class Task(BaseModel):
    """Одна задача: tasks/<категория>/<id>/ (task.yaml [+ tests.yaml] [+ canonical.bsl])."""

    id: str
    name: str
    category: str                    # "A" | "B"
    difficulty: str
    entry_point: str
    signature: str
    prompt: str
    dir: Path
    tests: TaskTests | None = None
    canonical: Path | None = None    # эталон, если есть
    m_testing: str | None = None     # пометка вроде pending_harness

    @property
    def testable(self) -> bool:
        """Есть ли у задачи скрытые тесты (ось M исполнима)."""
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


# ── расчёт Q ─────────────────────────────────────────────────────────────────

# Имя скорера в издании → буква оси конституции
SCORER_TO_AXIS = {"syntax": "S", "meaning": "M", "optimization": "O", "platform": "P"}


def compute_q(scores: dict[str, int | None], category: str,
              constitution: Constitution) -> float | None:
    """Q = среднее по ПРИМЕНИМЫМ осям (formula: mean_of_applicable).

    scores: {ось: балл | None}. None = ось не измерена (нет инструмента) —
    исключается из среднего, как и неприменимые к категории (см. гейтинг L1).
    """
    assert constitution.q_formula == "mean_of_applicable", constitution.q_formula
    applicable = constitution.applicable_axes(category)
    measured = [scores[a] for a in applicable if scores.get(a) is not None]
    if not measured:
        return None
    return round(sum(measured) / len(measured), 2)


# ── внутреннее ───────────────────────────────────────────────────────────────

def _read(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── самопроверка ─────────────────────────────────────────────────────────────

def main() -> None:
    const = load_constitution()
    proto = load_protocol_l1()
    tasks = load_tasks()
    edition = load_edition("core")
    gen = load_generation()

    print(f"конституция v{const.version}: оси {list(const.axes)}, "
          f"шкала {const.valid_scores}, Q={const.q_formula}")
    print(f"  применимо к A: {const.applicable_axes('A')}  |  "
          f"к B: {const.applicable_axes('B')}")
    print(f"протокол L1 v{proto.version}: "
          f"S reachable {proto.reachable('S')}, O веса: {len(proto.o_weights())} шт.")
    print(f"издание {edition.name}: mode={edition.mode}, context={edition.context}, "
          f"scorers={edition.scorers}")
    print(f"моделей в каталоге: {len(gen.models)} ({', '.join(gen.models)}); "
          f"system-промптов: {list(gen.prompts)}")
    print(f"задач: {len(tasks)}")
    for t in tasks:
        flags = [f"тестов: {len(t.tests.tests)}" if t.testable else "БЕЗ ТЕСТОВ"]
        if t.canonical:
            flags.append("эталон есть")
        if t.m_testing:
            flags.append(f"m_testing={t.m_testing}")
        print(f"  {t.id} [{t.category}/{t.difficulty}] {t.name} — {', '.join(flags)}")

    demo = compute_q({"S": 10, "M": 8, "O": 6, "P": None}, "A", const)
    print(f"проба Q (кат. A, S=10 M=8 O=6, P=N/A): {demo}  (ожидаем 8.0)")


if __name__ == "__main__":
    main()
