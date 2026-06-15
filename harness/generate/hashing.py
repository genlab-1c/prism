"""Хеширование ответов для анализа детерминизма (порт из core, самодостаточный).

Нормализация (извлечь код из ```-блока, срезать хвостовые пробелы и пустые края) →
SHA-256. Детерминизм = доля прогонов, совпавших с самым частым ответом.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

_CODE_BLOCK = re.compile(r"```(?:1c|1С|bsl|)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def normalize_code(text: str) -> str:
    """Извлечь код из markdown-блока и срезать незначимые пробелы/пустые края."""
    if not text:
        return ""
    m = _CODE_BLOCK.search(text)
    if m:
        text = m.group(1)
    lines = [ln.rstrip() for ln in text.strip().split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def compute_hash(text: str, *, normalize: bool = True) -> str:
    """SHA-256 (по умолчанию по нормализованному коду)."""
    if normalize:
        text = normalize_code(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_hashes(hashes: list[str]) -> dict:
    """Статистика детерминизма по хешам прогонов (match_rate — доля самого частого)."""
    if not hashes:
        return {"total_runs": 0, "unique_count": 0, "match_rate": 0.0,
                "most_common_hash": "", "most_common_count": 0}
    counter = Counter(hashes)
    most_common_hash, most_common_count = counter.most_common(1)[0]
    return {
        "total_runs": len(hashes),
        "unique_count": len(counter),
        "match_rate": most_common_count / len(hashes),
        "most_common_hash": most_common_hash,
        "most_common_count": most_common_count,
    }
