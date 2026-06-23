"""Прогон кандидата категории B против реальной 1С (синтетическая база, headless).

Петля (каждый шаг проверен исполнением):
 1. detect_entry_point — имя функции кандидата (та же детекция, что в категории A);
 2. assemble_run_config — база из config_spec.yaml + КодКандидата + Тесты + триггер;
 3. CREATEINFOBASE → /LoadConfigFromFiles → /UpdateDBCfg (обязателен);
 4. ENTERPRISE /C ПрогонТеста под Xvfb → обработчик пишет result.txt и выходит;
 5. parse_result — "PASSED=n;TOTAL=m;<лог>" → структура для скореров M/P.

Режим v1 — docker (образ с учебной 1С, без сети). Бинарь платформы на хосте
не предполагается. ВАЖНО: result.txt в контейнере пишется root'ом — раннер сам
делает chmod в том же контейнере (грабля «Permission denied → выглядит как пусто»).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from pydantic import BaseModel

DOCKER_IMAGE = "prism-onec:latest"
# Путь к бинарю учебного клиента — версия НЕ зашита: находим его глобом в рантайме внутри
# контейнера (подставляется в bash -c). Работает с образом любой версии 1С и не зависит от
# PATH (в части старых образов PATH к бинарю битый).
ONEC_BIN = '"$(ls /opt/1cv8t/x86_64/*/1cv8t 2>/dev/null | head -1)"'
STEP_TIMEOUT_S = 180  # на каждый шаг конфигуратора (DESIGNER) или клиента 1С
RESULT_RE = re.compile(r"PASSED=(\d+);TOTAL=(\d+);?(.*)", re.DOTALL)

# Маркеры платформенной ошибки в логе теста — сигнал оси P (ошибка обращения
# к метаданным/запросу), в отличие от просто неверного ответа (FAIL).
PLATFORM_ERROR_MARKERS = [
    "Поле не найдено",
    "Таблица не найдена",
    "Объект не найден",
    "не обнаружено",  # «Поле объекта не обнаружено»
    "Метод объекта не обнаружен",
    "Ошибка при вызове метода контекста (Выполнить)",  # ошибки исполнения запроса
]


class OneCRunResult(BaseModel):
    """Итог прогона одного кандидата B.

    Статусы различают ВИНУ (важно для гейтинга «нет инструмента → None, не 0»):
      ok              — прогон состоялся, passed/total валидны (вкл. 0/N);
      no_entry        — в коде кандидата нет функции (вина кандидата → 0);
      candidate_error — прогон не дал результата, и компиляция модуля кандидата
                        падает (вина кандидата → 0);
      no_result       — прогон не дал результата, кандидат компилируется —
                        похоже на инфраструктуру (→ None, «не измерено»);
      infra_error     — инфраструктура развалилась явно (→ None).
    """

    status: str  # ok | no_entry | candidate_error | no_result | infra_error
    passed: int = 0
    total: int = 0
    log: str = ""  # хвост result.txt: FAIL'ы и исключения тестов
    platform_errors: list[str] = []  # сработавшие маркеры платформенных ошибок
    platform_error_tests: int = 0  # сколько тестов упало именно платформенной ошибкой
    compile_error_lines: list[int] = []  # строки ошибок компиляции модуля кандидата (ось S)
    compile_errors: list[str] = []  # тексты ошибок компилятора (диагностика)
    entry_point: str | None = None
    infra_detail: str = ""  # диагностика инфраструктурных падений


def available() -> bool:
    """Docker + образ с платформой на месте."""
    if shutil.which("docker") is None:
        return False
    res = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True, text=True
    )
    return res.returncode == 0


def unavailable_reason() -> str:
    return f"нет docker или образа {DOCKER_IMAGE} (учебная 1С) — категория B пропущена"


_empty_cfg_lock = threading.Lock()


def _empty_cfg_cache() -> Path | None:
    """Выгрузка пустой конфигурации — общий кэш (work/_onec/empty-cfg)."""
    from harness.loaders import PRISM

    cache_root = PRISM / "work" / "_onec"
    cache = cache_root / "empty-cfg"
    if (cache / "Configuration.xml").exists():
        return cache
    with _empty_cfg_lock:  # под параллелизмом общий кэш собираем
        if (cache / "Configuration.xml").exists():  # один раз (двойная проверка под замком)
            return cache
        cache_root.mkdir(parents=True, exist_ok=True)
        res = _in_container(
            cache_root,
            (
                f"xvfb-run-1c {ONEC_BIN} CREATEINFOBASE 'File=/work/ib0;Locale=ru_RU;' >/dev/null 2>&1; "
                f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib0;' "
                f"/DumpConfigToFiles /work/empty-cfg >/dev/null 2>&1; "
                f"chmod -R a+rwX /work/empty-cfg /work/ib0 2>/dev/null; "
                f"test -f /work/empty-cfg/Configuration.xml && echo OK || echo FAIL"
            ),
            STEP_TIMEOUT_S * 2,
        )
        return cache if "OK" in res.stdout else None


def _in_container(work_dir: Path, script: str, timeout: int) -> subprocess.CompletedProcess:
    """Выполнить shell-скрипт в контейнере платформы с примонтированным work_dir.

    Контейнер именован: при таймауте python убивает только docker-клиента,
    сам контейнер продолжал бы жить зомби и душить следующие прогоны — добиваем явно.
    """
    name = f"prism-onec-{uuid.uuid4().hex[:12]}"
    # Лимиты ресурсов контейнера — опционально через env (полезно при параллельных
    # прогонах, чтобы 1С-клиенты не выели всю память). По умолчанию НЕ заданы →
    # поведение бит-в-бит как раньше. Нехватка лимита = «не измерено», не неверный балл.
    limits: list[str] = []
    if os.environ.get("PRISM_ONEC_MEMORY"):
        limits += ["--memory", os.environ["PRISM_ONEC_MEMORY"]]
    if os.environ.get("PRISM_ONEC_CPUS"):
        limits += ["--cpus", os.environ["PRISM_ONEC_CPUS"]]
    try:
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network=none",
                *limits,
                "-v",
                f"{work_dir}:/work",
                DOCKER_IMAGE,
                "bash",
                "-lc",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, text=True)
        raise


SUB_RE = re.compile(
    r"^\s*(?:Функция|Процедура)\s+([\wа-яА-ЯёЁ]+)\s*\(", re.MULTILINE | re.IGNORECASE
)


def detect_entry_point(code: str, patterns: list[str]) -> str | None:
    """Первая Функция ИЛИ Процедура, чьё имя матчится приоритетным паттерном.

    Шире детекции категории A (только функции): B-задачи бывают процедурами
    («заполнить ТЧ», «пересчитать суммы»), меняющими аргументы по месту.
    """
    names = SUB_RE.findall(code)
    if not names:
        return None
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for name in names:  # порядок объявления = приоритет
            if rx.fullmatch(name):
                return name
    return names[0]


def run_candidate(
    candidate_code: str, task_dir: Path, work_dir: Path, entry_patterns: list[str]
) -> OneCRunResult:
    """Полный прогон одного кандидата B: сборка → база → исполнение → результат."""
    from .assemble import assemble_run_config

    entry = detect_entry_point(candidate_code, entry_patterns)
    if entry is None:
        return OneCRunResult(
            status="no_entry", infra_detail="в коде кандидата не найдено ни одной функции"
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) пустая конфа-базис: выгружается платформой ОДИН раз на машину
    #    (общий кэш в work/), в work_dir кандидата попадает копией — иначе
    #    каждый кандидат платит ~50с за идентичную выгрузку.
    empty_cfg = work_dir / "empty-cfg"
    if not (empty_cfg / "Configuration.xml").exists():
        cache = _empty_cfg_cache()
        if cache is None:
            return OneCRunResult(
                status="infra_error",
                entry_point=entry,
                infra_detail="не удалось выгрузить пустую конфигурацию (кэш)",
            )
        shutil.copytree(cache, empty_cfg, dirs_exist_ok=True)

    # 2) сборка прогонной конфы (на хосте, чистый Python)
    assemble_run_config(task_dir, candidate_code, entry, empty_cfg, work_dir / "run-cfg")

    # 3) база + компиляция (S) + исполнение (M/P) — один вызов контейнера.
    # /CheckModules даёт ось S (ошибки модуля КодКандидата); если кандидат не
    # компилируется — ENTERPRISE не запускаем (быстрее и честно: M/P = 0).
    # На ENTERPRISE свой timeout 90: чужой дефект не должен висеть.
    # CheckModules проверяет конфигурацию БД → строго ПОСЛЕ UpdateDBCfg; оба
    # безусловно после успешного load (через ;), чтобы ошибки кандидата всплыли,
    # даже если UpdateDBCfg споткнулся. ENTERPRISE — только при чистой компиляции.
    script = (
        f"rm -rf /work/ib /work/result.txt /work/check.log; "
        f"xvfb-run-1c {ONEC_BIN} CREATEINFOBASE 'File=/work/ib;Locale=ru_RU;' >/dev/null 2>&1 && "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/LoadConfigFromFiles /work/run-cfg /Out /work/load.log >/dev/null 2>&1 && {{ "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/UpdateDBCfg /Out /work/upd.log >/dev/null 2>&1; "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/CheckModules -Server /Out /work/check.log >/dev/null 2>&1; "
        f"if grep -q 'КодКандидата' /work/check.log 2>/dev/null; then true; else "
        f"timeout 90 xvfb-run-1c {ONEC_BIN} ENTERPRISE /IBConnectionString 'File=/work/ib;' "
        f"/C ПрогонТеста >/dev/null 2>&1; fi; }}; "
        f"chmod -R a+rwX /work 2>/dev/null; true"
    )
    timed_out = False
    try:
        _in_container(work_dir, script, STEP_TIMEOUT_S * 3)
    except subprocess.TimeoutExpired:
        timed_out = True

    # ось S — ошибки компиляции модуля кандидата (компилятор 1С, не статика)
    lines, errors = _parse_compile_log(_read(work_dir / "check.log"))
    if lines:  # не компилируется → вина кандидата
        return OneCRunResult(
            status="candidate_error",
            entry_point=entry,
            compile_error_lines=lines,
            compile_errors=errors[:5],
            log="; ".join(errors[:3])[:500],
            infra_detail="модуль кандидата не компилируется",
        )

    # компилируется → M/P из result.txt
    result_file = work_dir / "result.txt"
    if result_file.exists():
        return parse_result(result_file.read_text(encoding="utf-8-sig", errors="replace"), entry)

    detail = "таймаут прогона" if timed_out else "result.txt не создан"
    return OneCRunResult(
        status="no_result",
        entry_point=entry,
        infra_detail=f"{detail}; load.log: {_read(work_dir / 'load.log')[:200]}",
    )


# лог /CheckModules: «{ОбщийМодуль.КодКандидата.Модуль(строка,колонка)}: Сообщение»
_COMPILE_RE = re.compile(r"\{ОбщийМодуль\.КодКандидата\.Модуль\((\d+)(?:,\s*\d+)?\)\}\s*:?\s*(.*)")


def _read(path: Path) -> str:
    # При таймауте контейнера финальный chmod не успевает отработать → логи остаются
    # root:640 (ловушка headless-1С). Диагностика не должна ронять весь прогон —
    # недоступный лог отдаём пустым (статус прогона и так будет no_result/таймаут).
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace") if path.exists() else ""
    except OSError:
        return ""


def _parse_compile_log(text: str) -> tuple[list[int], list[str]]:
    """Из лога /CheckModules → (строки ошибок модуля кандидата, тексты ошибок)."""
    lines, errors = [], []
    for m in _COMPILE_RE.finditer(text or ""):
        lines.append(int(m.group(1)))
        errors.append(m.group(2).strip()[:200])
    return lines, errors


def parse_result(text: str, entry: str | None = None) -> OneCRunResult:
    """Разбор "PASSED=n;TOTAL=m;<лог>" + классификация платформенных ошибок (сигнал P)."""
    text = text.strip()
    m = RESULT_RE.search(text)
    if not m:
        # обработчик упал до тестов (КЛИЕНТ_ИСКЛЮЧЕНИЕ и т.п.)
        markers = [p for p in PLATFORM_ERROR_MARKERS if p.lower() in text.lower()]
        return OneCRunResult(
            status="ok",
            passed=0,
            total=0,
            log=text[:500],
            platform_errors=markers,
            entry_point=entry,
        )
    log = m.group(3).strip()
    markers = [p for p in PLATFORM_ERROR_MARKERS if p.lower() in log.lower()]
    return OneCRunResult(
        status="ok",
        passed=int(m.group(1)),
        total=int(m.group(2)),
        log=log[:500],
        platform_errors=markers,
        platform_error_tests=_count_platform_error_tests(log),
        entry_point=entry,
    )


def _count_platform_error_tests(log: str) -> int:
    """Сколько тестов упало платформенной ошибкой (сигнал P — clean/total).

    Лог формата «тестN ИСКЛЮЧЕНИЕ: …; тестM FAIL …»: режем по началам записей
    «тестN » и ищем маркеры внутри каждого сегмента. FAIL по значению (неверный
    ответ) платформенной ошибкой не считается — это территория оси M.
    """
    segments = re.split(r"(?=тест\d+\s)", log)
    count = 0
    for seg in segments:
        if not re.match(r"тест\d+\s+ИСКЛЮЧЕНИЕ", seg):
            continue
        if any(p.lower() in seg.lower() for p in PLATFORM_ERROR_MARKERS):
            count += 1
    return count
