"""Инструмент осей S/O: BSL Language Server в режиме analyze → JSON-диагностики.

Два режима, как у раннера OneScript (execute/runner.py) — выбор через env PRISM_BSL:
  local  — java -jar из tools/ прямо на хосте (нужен JRE 21+). Для своей разработки.
  docker — образ prism-bsl-ls (docker/bsl-ls.Dockerfile): JRE внутри, без сети,
           код смонтирован read-only. Для CI и недоверенных кандидатов.

BSL LS только ПАРСИТ код (не исполняет), поэтому риск ниже, чем у M, и local на хосте
допустим даже для чужого кода; docker — ради воспроизводимости и единого пинового JRE.

Один батч-запуск на всё дерево исходников (старт JVM ~секунды — per-file дорого).
Отчёт: <out_dir>/bsl-json.json, fileinfos[{path, diagnostics[{code, severity, …}]}].

Гейтинг как у раннера: инструмент недоступен → ось S/O «не измерена» (score=None),
НЕ ноль (решается выше по стеку, в оркестраторе).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import BaseModel

from harness.loaders import PRISM

VERSION = "0.29.0"
JAR = PRISM / "tools" / f"bsl-language-server-{VERSION}-exec.jar"
DOCKER_IMAGE = f"prism-bsl-ls:{VERSION}"
TIMEOUT_S = 600

# Кандидаты на java 21+ (jar собран под Java 21): env → типовые пути дистрибутива
_JAVA_CANDIDATES = [
    os.environ.get("PRISM_JAVA"),
    "/usr/lib/jvm/java-21-openjdk/bin/java",
    "/usr/lib/jvm/java-24-openjdk/bin/java",
]

# Аргументы analyze, общие для обоих режимов (пути src/out подставляет режим)
_ANALYZE = ["analyze", "--silent", "--reporter", "json"]


def java_bin() -> str | None:
    """Первый существующий java из кандидатов (None — не нашли)."""
    for cand in _JAVA_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return None


class LocalBSL(BaseModel):
    """BSL LS на хосте: java -jar из tools/."""

    name: str = "local"

    def available(self) -> bool:
        return JAR.exists() and java_bin() is not None

    def unavailable_reason(self) -> str:
        if not JAR.exists():
            return f"нет {JAR.name} — ./tools/get-bsl-ls.sh"
        return "не найден java 21+ — задайте PRISM_JAVA"

    def describe(self) -> str:
        return f"BSL LS {VERSION} · {java_bin()} (local)"

    def analyze(self, src_dir: Path, out_dir: Path) -> dict[str, list[dict]]:
        cmd = [
            java_bin(),
            "-jar",
            str(JAR),
            *_ANALYZE,
            "--srcDir",
            str(src_dir),
            "--outputDir",
            str(out_dir),
        ]
        return _run_and_parse(cmd, out_dir)


class DockerBSL(BaseModel):
    """BSL LS в песочнице: JRE внутри образа, без сети, ro-mount исходников."""

    name: str = "docker"
    image: str = DOCKER_IMAGE

    def available(self) -> bool:
        try:
            return (
                subprocess.run(
                    ["docker", "image", "inspect", self.image], capture_output=True, timeout=10
                ).returncode
                == 0
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def unavailable_reason(self) -> str:
        return (
            f"нет docker-образа {self.image} — "
            f"docker build -t {self.image} -f docker/bsl-ls.Dockerfile ."
        )

    def describe(self) -> str:
        return f"BSL LS {VERSION} · {self.image} (docker)"

    def analyze(self, src_dir: Path, out_dir: Path) -> dict[str, list[dict]]:
        src_dir, out_dir = src_dir.resolve(), out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        # --user uid хоста: чтобы bsl-json.json в /out был читаем на хосте (как DockerRunner)
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{src_dir}:/src:ro",
            "-v",
            f"{out_dir}:/out",
            self.image,
            *_ANALYZE,
            "--srcDir",
            "/src",
            "--outputDir",
            "/out",
        ]
        return _run_and_parse(cmd, out_dir)


BSL = LocalBSL | DockerBSL


def get_analyzer(mode: str | None = None) -> BSL:
    """Фабрика по режиму: аргумент → env PRISM_BSL → local."""
    mode = (mode or os.environ.get("PRISM_BSL") or "local").lower()
    if mode == "local":
        return LocalBSL()
    if mode == "docker":
        return DockerBSL()
    raise ValueError(f"неизвестный режим BSL LS: {mode!r} (local | docker)")


# ── фасад (стабильный модульный API для оркестратора/чека) ───────────────────


def available() -> bool:
    return get_analyzer().available()


def unavailable_reason() -> str:
    return get_analyzer().unavailable_reason()


def describe() -> str:
    return get_analyzer().describe()


def analyze(src_dir: Path, out_dir: Path) -> dict[str, list[dict]]:
    """Прогнать BSL LS (режим из PRISM_BSL) по дереву src_dir; {имя_файла: диагностики}.

    Ключ — basename: BSL LS пишет пути относительно своего CWD, а батч идёт по
    плоской папке с уникальными именами (их гарантирует вызывающий, оркестратор).
    """
    return get_analyzer().analyze(src_dir, out_dir)


# ── внутреннее ───────────────────────────────────────────────────────────────


def _run_and_parse(cmd: list[str], out_dir: Path) -> dict[str, list[dict]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    report_path = out_dir / "bsl-json.json"
    if not report_path.exists():
        raise RuntimeError(
            f"BSL LS не создал отчёт (rc={proc.returncode}).\nstderr: {proc.stderr[-2000:]}"
        )
    report = _read_json(report_path)
    return {
        _basename(info["path"]): [_norm(d) for d in info.get("diagnostics", [])]
        for info in report.get("fileinfos", [])
    }


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
        "severity": str(diag.get("severity", "")).lower(),  # error|warning|information|hint
        "message": diag.get("message", ""),
        "line": start.get("line", -1) + 1,
    }


def _read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8-sig"))
