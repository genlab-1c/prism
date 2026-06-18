"""Режимы исполнения кода кандидатов: local | docker.

Режим — ИНФРАСТРУКТУРА, не идентичность результата: баллы не зависят от способа
запуска (тот же OneScript), поэтому режим не входит в «версия × издание × конфиг»
и не живёт в editions/. Выбор — env PRISM_RUNNER (local по умолчанию) или явно.

  local  — oscript из tools/ прямо на хосте. Быстро; для своей разработки.
  docker — образ prism-onescript (docker/onescript.Dockerfile): без сети,
           лимиты CPU/память, код смонтирован read-only. Для CI и чужих
           кандидатов: код LLM недоверенный, у OneScript есть доступ к ФС/сети.

Скореры не знают о режимах — зовут runner.run_os(file) и получают результат.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from pydantic import BaseModel

from harness.loaders import PRISM

OSCRIPT = PRISM / "tools" / "onescript" / "bin" / "oscript"
DOCKER_IMAGE = "prism-onescript:2.0.1"
TIMEOUT_S = 15

# Лимиты docker-песочницы
SANDBOX_OPTS = ["--network=none", "--memory=256m", "--cpus=1", "--pids-limit=128"]


class ExecResult(BaseModel):
    """Итог запуска .os-файла."""

    stdout: str = ""
    stderr: str = ""
    rc: int | None = None  # None = таймаут
    timed_out: bool = False


class LocalRunner(BaseModel):
    """oscript на хосте (tools/get-onescript.sh)."""

    name: str = "local"

    def available(self) -> bool:
        return OSCRIPT.exists()

    def unavailable_reason(self) -> str:
        return "oscript не установлен — ./tools/get-onescript.sh"

    def run_os(self, script: Path, timeout: int = TIMEOUT_S) -> ExecResult:
        try:
            proc = subprocess.run(
                [str(OSCRIPT), str(script)], capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return ExecResult(timed_out=True)
        return ExecResult(stdout=proc.stdout, stderr=proc.stderr, rc=proc.returncode)


class DockerRunner(BaseModel):
    """oscript в песочнице: без сети, лимиты, read-only монтирование кода."""

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
            f"docker build -t {self.image} -f docker/onescript.Dockerfile ."
        )

    def run_os(self, script: Path, timeout: int = TIMEOUT_S) -> ExecResult:
        script = script.resolve()
        container = f"prism-os-{uuid.uuid4().hex[:12]}"
        # --user uid хоста: иначе контейнерный пользователь не прочитает каталоги 0700
        # (например, pytest tmp_path); непривилегированность сохраняется
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container,
            *SANDBOX_OPTS,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{script.parent}:/sandbox:ro",
            self.image,
            "oscript",
            f"/sandbox/{script.name}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout + 10
            )  # запас на старт контейнера
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            return ExecResult(timed_out=True)
        return ExecResult(stdout=proc.stdout, stderr=proc.stderr, rc=proc.returncode)


Runner = LocalRunner | DockerRunner


def get_runner(mode: str | None = None) -> Runner:
    """Фабрика по режиму: аргумент → env PRISM_RUNNER → local."""
    mode = (mode or os.environ.get("PRISM_RUNNER") or "local").lower()
    if mode == "local":
        return LocalRunner()
    if mode == "docker":
        return DockerRunner()
    raise ValueError(f"неизвестный режим исполнения: {mode!r} (local | docker)")
