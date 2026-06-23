"""Упаковка результата прогона для шеринга (prism submit) и приём чужого (--verify/--apply).

Идея: оценки L1 несравнимы между разными версиями бенчмарка (другая метрика или другой
набор задач → другие числа). Поэтому к результату прикладывается compat_hash — отпечаток
ВЕРСИИ бенчмарка (конституция + протокол L1 + набор задач и их условия/проверки). Автор,
принимая пакет, сверяет отпечаток со своим репозиторием: совпал — можно вливать в
results/auto/ и пересобирать лидерборд (prism docs); не совпал — прогон на другой версии.

Транспорт намеренно простой: файл в results/submissions/, который прикладывают к PR или
присылают автору. Никакой серверной инфраструктуры.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.generate.hashing import compute_hash
from harness.loaders import PRISM, load_constitution, load_protocol_l1, load_tasks
from harness.orchestrate import newest_auto

SCHEMA_VERSION = 1

# Файлы задачи, определяющие сравнимость прогона (условие + скрытые проверки).
# canonical.bsl НЕ входит: эталон — не то, что измеряется у кандидата.
_TASK_FILES = ("task.yaml", "tests.yaml", "tests.bsl", "config_spec.yaml", "fixtures.yaml")

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("prism-bench")
except Exception:  # noqa: BLE001
    _VERSION = "dev"


def benchmark_fingerprint() -> str:
    """Отпечаток версии бенчмарка: метрика + набор задач и их условия/проверки.

    Меняется, если поменялась конституция/протокол ИЛИ любой файл условия/проверок любой
    задачи, ИЛИ состав банка. Именно это делает оценки сравнимыми (или нет)."""
    const = load_constitution()
    proto = load_protocol_l1()
    parts = [f"constitution={const.version}", f"protocol={proto.version}"]
    for t in sorted(load_tasks(), key=lambda t: t.id):
        digests = []
        for fname in _TASK_FILES:
            p = t.dir / fname
            if p.exists():
                digests.append(
                    f"{fname}:{compute_hash(p.read_text(encoding='utf-8-sig'), normalize=False)}"
                )
        parts.append(f"{t.id}|" + ",".join(digests))
    return compute_hash("\n".join(parts), normalize=False)


def _models_in(result: dict) -> list[str]:
    seen: dict[str, None] = {}
    for t in result.get("tasks", []):
        seen.setdefault(t.get("model_name", t.get("model_id", "?")), None)
    return list(seen)


def build_submission(auto_path: Path | None = None, created: str = "") -> tuple[Path, dict]:
    """Собрать пакет из готовой авто-оценки L1 → results/submissions/<exp>_submission.json."""
    auto_path = auto_path or newest_auto()
    result = json.loads(auto_path.read_text(encoding="utf-8"))
    submission = {
        "schema_version": SCHEMA_VERSION,
        "prism_version": _VERSION,
        "created": created,
        "experiment_id": result["experiment_id"],
        "compat_hash": benchmark_fingerprint(),
        "versions": {
            "constitution": result.get("constitution_version"),
            "protocol": result.get("protocol_version"),
            "runner": result.get("runner"),
            "syntax_analyzer": result.get("syntax_analyzer"),
        },
        "models": _models_in(result),
        "result": result,
    }
    out = PRISM / "results" / "submissions" / f"{result['experiment_id']}_submission.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, submission


def verify_submission(path: Path) -> dict:
    """Сверить отпечаток пакета с текущим репозиторием.

    {compatible, current_hash, submission}. compatible — можно ли вливать без оговорок."""
    submission = json.loads(path.read_text(encoding="utf-8"))
    current = benchmark_fingerprint()
    return {
        "compatible": submission.get("compat_hash") == current,
        "current_hash": current,
        "submission": submission,
    }


def apply_submission(submission: dict) -> Path:
    """Положить оценку из пакета в results/auto/ (дальше лидерборд пересобирает prism docs)."""
    result = submission["result"]
    out = PRISM / "results" / "auto" / f"{result['experiment_id']}_auto_l1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
