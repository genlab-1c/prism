"""Инструмент оси S/O: BSL Language Server в режиме analyze → JSON-диагностики.

Один батч-запуск JVM на всё дерево исходников (старт JVM ~секунды — per-file дорого).
Отчёт: <out_dir>/bsl-json.json, fileinfos[{path, diagnostics[{code, severity, …}]}].

Гейтинг как у раннера (execute/runner.py): нет Java 21+ или jar — инструмент
недоступен, ось S «не измерена» (score=None), НЕ ноль. Java и версия jar —
ИНФРАСТРУКТУРА (не идентичность балла), поэтому через env, а не editions/:
  PRISM_JAVA  — путь к java (по умолчанию ищем java-21 в /usr/lib/jvm)
  jar         — tools/bsl-language-server-<версия>-exec.jar (ставит tools/get-bsl-ls.sh)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from harness.loaders import PRISM

VERSION = "0.29.0"
JAR = PRISM / "tools" / f"bsl-language-server-{VERSION}-exec.jar"
TIMEOUT_S = 600

# Кандидаты на java 21+ (jar собран под Java 21): env → типовые пути дистрибутива
_JAVA_CANDIDATES = [
    os.environ.get("PRISM_JAVA"),
    "/usr/lib/jvm/java-21-openjdk/bin/java",
    "/usr/lib/jvm/java-24-openjdk/bin/java",
]


def java_bin() -> str | None:
    """Первый существующий java из кандидатов (None — не нашли)."""
    for cand in _JAVA_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return None


def available() -> bool:
    return JAR.exists() and java_bin() is not None


def unavailable_reason() -> str:
    if not JAR.exists():
        return f"нет {JAR.name} — ./tools/get-bsl-ls.sh"
    return "не найден java 21+ — задайте PRISM_JAVA"


def analyze(src_dir: Path, out_dir: Path) -> dict[str, list[dict]]:
    """Прогнать BSL LS по дереву src_dir; вернуть {имя_файла: [диагностики]}.

    Ключ — basename: BSL LS пишет пути относительно CWD (не src_dir), а батч идёт
    по плоской папке с уникальными именами (их гарантирует вызывающий, оркестратор).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [java_bin(), "-jar", str(JAR), "analyze", "--silent",
           "--srcDir", str(src_dir), "--outputDir", str(out_dir), "--reporter", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    report_path = out_dir / "bsl-json.json"
    if not report_path.exists():
        raise RuntimeError(f"BSL LS не создал отчёт (rc={proc.returncode}).\n"
                           f"stderr: {proc.stderr[-2000:]}")
    report = _read_json(report_path)
    result: dict[str, list[dict]] = {}
    for info in report.get("fileinfos", []):
        result[_basename(info["path"])] = [_norm(d) for d in info.get("diagnostics", [])]
    return result


# ── внутреннее ───────────────────────────────────────────────────────────────

def _basename(raw: str) -> str:
    """Имя файла из пути BSL LS (бывает file:// URI)."""
    if raw.startswith("file://"):
        raw = unquote(urlparse(raw).path)
    return Path(raw).name


def _norm(diag: dict) -> dict:
    """Диагностика → {code, severity, message, line}. code бывает Either-объектом."""
    code = diag.get("code")
    if isinstance(code, dict):
        code = code.get("stringValue") or code.get("left") or code.get("right") or str(code)
    start = diag.get("range", {}).get("start", {})
    return {
        "code": str(code),
        "severity": str(diag.get("severity", "")).lower(),   # error|warning|information|hint
        "message": diag.get("message", ""),
        "line": start.get("line", -1) + 1,
    }


def _read_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8-sig"))
