"""Режимы исполнения кода кандидатов: local | docker.

Режим — ИНФРАСТРУКТУРА, не идентичность результата: баллы не зависят от способа
запуска (тот же OneScript), поэтому режим не входит в «версия × издание × конфиг»
и не живёт в editions/. Выбор — env PRISM_RUNNER (docker по умолчанию) или явно.

  docker — образ prism-onescript (docker/onescript.Dockerfile): без сети,
           лимиты CPU/память, код смонтирован read-only. ДЕФОЛТ: код LLM
           недоверенный, у OneScript есть доступ к ФС/сети — гоняем в песочнице.
  local  — oscript из tools/ прямо на хосте. Быстро; для своей разработки
           (явно: --runner local или PRISM_RUNNER=local).

Скореры не знают о режимах — зовут runner.run_os(file) и получают результат.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from pydantic import BaseModel

from harness.execute import measure_cache
from harness.loaders import PRISM

OSCRIPT = PRISM / "tools" / "onescript" / "bin" / "oscript"
DOCKER_IMAGE = "prism-onescript:2.0.1"
TIMEOUT_S = 15  # бюджет ПРОЦЕССОРНОГО времени (см. cpu_limit_s протокола)
# Сторож по настенным часам: во столько раз больше процессорного бюджета. Нужен только против
# зависаний (процесс, который ничего не считает, процессорное время не тратит). Его срабатывание
# означает «не измерено», а не «медленно»: под нагрузкой настенное время растягивается, и делать из
# него вердикт значит ставить балл в зависимость от того, чем ещё занята машина.
WALL_FACTOR = 5
# Среда .NET игнорирует мягкий сигнал об исчерпании процессорного времени и умирает лишь на
# жёстком лимите. Поэтому оболочку в контейнере НЕ заменяем через exec: она переживает дочерний
# процесс и сообщает отличимый код 152 вместо общего «убит» (137), который не отличить от
# нехватки памяти. Проверено: три прогона подряд дают 152, обычный скрипт по-прежнему даёт 0.
SIGXCPU_RC = 152  # 128 + 24: дочерний процесс исчерпал процессорный бюджет

# Лимиты docker-песочницы
SANDBOX_OPTS = ["--network=none", "--memory=256m", "--cpus=1", "--pids-limit=128"]


class ExecResult(BaseModel):
    """Итог запуска .os-файла."""

    stdout: str = ""
    stderr: str = ""
    rc: int | None = None  # None = таймаут
    timed_out: bool = False  # сторож по НАСТЕННЫМ часам: сбой окружения, «не измерено»
    cpu_exhausted: bool = False  # исчерпан бюджет ПРОЦЕССОРНОГО времени: свойство кода, не машины


def _cpu_limiter(cpu_seconds: int):
    """Ограничить ПРОЦЕССОРНОЕ время дочернего процесса.

    Мягкий лимит ниже жёсткого даёт отличимый код возврата 152 вместо общего «убит»: так
    «кандидат исчерпал бюджет» не путается с нехваткой памяти или падением окружения.
    """

    def apply() -> None:  # pragma: no cover — исполняется в дочернем процессе
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 10))

    return apply


def _with_cpu_flag(proc) -> ExecResult:
    """Результат процесса с признаком «исчерпан процессорный бюджет»."""
    return ExecResult(
        stdout=proc.stdout,
        stderr=proc.stderr,
        rc=proc.returncode,
        # docker отдаёт 152 (оболочка сообщила о сигнале), локальный запуск — отрицательный
        # код сигнала: -24 если сигнал дошёл, -9 если среда его пережила до жёсткого лимита
        cpu_exhausted=proc.returncode in (SIGXCPU_RC, -24, -9),
    )


def _cache_key(kind: str, script: Path, tag: str, limit: int) -> str | None:
    """Ключ замера: ТЕКСТ скрипта, метка инструмента и БЮДЖЕТ процессорного времени.

    Скрипт собран харнессом из кода кандидата, скрытых тестов и логики сборки, поэтому
    изменение любой из частей меняет текст, а с ним и ключ — кэш инвалидируется сам.
    Бюджет в ключе обязателен: при другом лимите тот же скрипт даёт другой исход
    (уложился или исчерпал), и без него кэш вернул бы ответ от прежнего лимита.
    Не смогли прочитать файл — считаем без кэша (None).
    """
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return measure_cache.key(kind, text, tag, str(limit))


class LocalRunner(BaseModel):
    """oscript на хосте (tools/get-onescript.sh)."""

    name: str = "local"

    @property
    def tag(self) -> str:
        """Метка версии инструмента для ключа кэша: путь и размер бинаря oscript."""
        try:
            return f"local:{OSCRIPT}:{OSCRIPT.stat().st_size}"
        except OSError:
            return "local:?"

    def available(self) -> bool:
        return OSCRIPT.exists()

    def unavailable_reason(self) -> str:
        return "oscript не установлен — ./tools/get-onescript.sh"

    def run_os(self, script: Path, timeout: int = TIMEOUT_S) -> ExecResult:
        k = _cache_key("run_os", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:
            return ExecResult(**hit)
        try:
            proc = subprocess.run(
                [str(OSCRIPT), str(script)],
                capture_output=True,
                text=True,
                timeout=timeout * WALL_FACTOR,
                preexec_fn=_cpu_limiter(timeout),
            )
        except subprocess.TimeoutExpired:
            return ExecResult(timed_out=True)  # сторож по часам: свойство машины, не кэшируем
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, res.model_dump())
        return res

    def check_os(self, script: Path, timeout: int = TIMEOUT_S) -> ExecResult:
        """Только разбор и компиляция, без исполнения (`oscript -check`) — вердикт оси S."""
        k = _cache_key("check_os", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:
            return ExecResult(**hit)
        try:
            proc = subprocess.run(
                [str(OSCRIPT), "-check", str(script)],
                capture_output=True,
                text=True,
                timeout=timeout * WALL_FACTOR,
                preexec_fn=_cpu_limiter(timeout),
            )
        except subprocess.TimeoutExpired:
            return ExecResult(timed_out=True)
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, res.model_dump())
        return res

    def run_os_codestat(
        self, script: Path, stat_path: Path, timeout: int = TIMEOUT_S
    ) -> ExecResult:
        """Как run_os, но с -codestat: oscript пишет в stat_path счётчик строк (ось O-исп.)."""
        k = _cache_key("codestat", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:  # вместе с выводом восстанавливаем и файл счётчиков
            stat_path.parent.mkdir(parents=True, exist_ok=True)
            stat_path.write_text(hit.pop("_stat", ""), encoding="utf-8")
            return ExecResult(**hit)
        try:
            proc = subprocess.run(
                [str(OSCRIPT), f"-codestat={stat_path}", str(script)],
                capture_output=True,
                text=True,
                timeout=timeout * WALL_FACTOR,
                preexec_fn=_cpu_limiter(timeout),
            )
        except subprocess.TimeoutExpired:
            return ExecResult(timed_out=True)
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, {**res.model_dump(), "_stat": _read_text(stat_path)})
        return res


class DockerRunner(BaseModel):
    """oscript в песочнице: без сети, лимиты, read-only монтирование кода."""

    name: str = "docker"
    image: str = DOCKER_IMAGE

    @property
    def tag(self) -> str:
        """Метка версии инструмента для ключа кэша: тег образа."""
        return self.image

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
        k = _cache_key("run_os", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:
            return ExecResult(**hit)
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
            "sh",
            "-c",
            f"ulimit -S -t {timeout}; ulimit -H -t {timeout + 10}; oscript /sandbox/{script.name}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout * WALL_FACTOR + 10
            )  # сторож по часам с запасом на старт контейнера
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            return ExecResult(timed_out=True)  # сторож по часам — свойство машины, не входа
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, res.model_dump())
        return res

    def check_os(self, script: Path, timeout: int = TIMEOUT_S) -> ExecResult:
        """Только разбор и компиляция, без исполнения (`oscript -check`) — вердикт оси S."""
        script = script.resolve()
        k = _cache_key("check_os", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:
            return ExecResult(**hit)
        container = f"prism-os-{uuid.uuid4().hex[:12]}"
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
            "sh",
            "-c",
            f"ulimit -S -t {timeout}; ulimit -H -t {timeout + 10}; "
            f"oscript -check /sandbox/{script.name}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout * WALL_FACTOR + 10
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            return ExecResult(timed_out=True)
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, res.model_dump())
        return res

    def run_os_codestat(
        self, script: Path, stat_path: Path, timeout: int = TIMEOUT_S
    ) -> ExecResult:
        """Как run_os, но с -codestat. Код смонтирован ro (/sandbox), отчёт пишется в
        rw-каталог /out — чтобы недоверенный кандидат не писал в каталог с кодом."""
        k = _cache_key("codestat", script, self.tag, timeout)
        hit = measure_cache.get(k) if k else None
        if hit is not None:  # вместе с выводом восстанавливаем и файл счётчиков
            stat_path.parent.mkdir(parents=True, exist_ok=True)
            stat_path.write_text(hit.pop("_stat", ""), encoding="utf-8")
            return ExecResult(**hit)
        script, stat_path = script.resolve(), stat_path.resolve()
        stat_path.parent.mkdir(parents=True, exist_ok=True)
        container = f"prism-os-{uuid.uuid4().hex[:12]}"
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
            "-v",
            f"{stat_path.parent}:/out",
            self.image,
            "sh",
            "-c",
            f"ulimit -S -t {timeout}; ulimit -H -t {timeout + 10}; "
            f"oscript -codestat=/out/{stat_path.name} /sandbox/{script.name}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout * WALL_FACTOR + 10
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            return ExecResult(timed_out=True)
        res = _with_cpu_flag(proc)
        if k:
            measure_cache.put(k, {**res.model_dump(), "_stat": _read_text(stat_path)})
        return res


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


Runner = LocalRunner | DockerRunner


def get_runner(mode: str | None = None) -> Runner:
    """Фабрика по режиму: аргумент → env PRISM_RUNNER → docker (песочница по умолчанию)."""
    mode = (mode or os.environ.get("PRISM_RUNNER") or "docker").lower()
    if mode == "local":
        return LocalRunner()
    if mode == "docker":
        return DockerRunner()
    raise ValueError(f"неизвестный режим исполнения: {mode!r} (local | docker)")
