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

import re
import shutil
import subprocess
import uuid
from pathlib import Path

from pydantic import BaseModel

DOCKER_IMAGE = "prism-onec:latest"
ONEC_BIN = "/opt/1cv8t/x86_64/8.3.27.1508/1cv8t"
STEP_TIMEOUT_S = 180          # на каждый шаг ДИЗАЙНЕРА/клиента
RESULT_RE = re.compile(r"PASSED=(\d+);TOTAL=(\d+);?(.*)", re.DOTALL)

# Маркеры платформенной ошибки в логе теста — сигнал оси P (ошибка обращения
# к метаданным/запросу), в отличие от просто неверного ответа (FAIL).
PLATFORM_ERROR_MARKERS = [
    "Поле не найдено",
    "Таблица не найдена",
    "Объект не найден",
    "не обнаружено",          # «Поле объекта не обнаружено»
    "Метод объекта не обнаружен",
    "Ошибка при вызове метода контекста (Выполнить)",   # ошибки исполнения запроса
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

    status: str                     # ok | no_entry | candidate_error | no_result | infra_error
    passed: int = 0
    total: int = 0
    log: str = ""                   # хвост result.txt: FAIL'ы и исключения тестов
    platform_errors: list[str] = []  # сработавшие маркеры платформенных ошибок
    platform_error_tests: int = 0   # сколько тестов упало именно платформенной ошибкой
    entry_point: str | None = None
    infra_detail: str = ""          # диагностика инфраструктурных падений


def available() -> bool:
    """Docker + образ с платформой на месте."""
    if shutil.which("docker") is None:
        return False
    res = subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE],
                         capture_output=True, text=True)
    return res.returncode == 0


def unavailable_reason() -> str:
    return f"нет docker или образа {DOCKER_IMAGE} (учебная 1С) — категория B пропущена"


def _empty_cfg_cache() -> Path | None:
    """Выгрузка пустой конфигурации — общий кэш (work/_onec/empty-cfg)."""
    from harness.loaders import PRISM
    cache_root = PRISM / "work" / "_onec"
    cache = cache_root / "empty-cfg"
    if (cache / "Configuration.xml").exists():
        return cache
    cache_root.mkdir(parents=True, exist_ok=True)
    res = _in_container(cache_root, (
        f"xvfb-run-1c {ONEC_BIN} CREATEINFOBASE 'File=/work/ib0;Locale=ru_RU;' >/dev/null 2>&1; "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib0;' "
        f"/DumpConfigToFiles /work/empty-cfg >/dev/null 2>&1; "
        f"chmod -R a+rwX /work/empty-cfg /work/ib0 2>/dev/null; "
        f"test -f /work/empty-cfg/Configuration.xml && echo OK || echo FAIL"
    ), STEP_TIMEOUT_S * 2)
    return cache if "OK" in res.stdout else None


def _in_container(work_dir: Path, script: str, timeout: int) -> subprocess.CompletedProcess:
    """Выполнить shell-скрипт в контейнере платформы с примонтированным work_dir.

    Контейнер именован: при таймауте python убивает только docker-клиента,
    сам контейнер продолжал бы жить зомби и душить следующие прогоны — добиваем явно.
    """
    name = f"prism-onec-{uuid.uuid4().hex[:12]}"
    try:
        return subprocess.run(
            ["docker", "run", "--rm", "--name", name, "--network=none",
             "-v", f"{work_dir}:/work", DOCKER_IMAGE, "bash", "-lc", script],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, text=True)
        raise


SUB_RE = re.compile(r"^\s*(?:Функция|Процедура)\s+([\wа-яА-ЯёЁ]+)\s*\(",
                    re.MULTILINE | re.IGNORECASE)


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
        for name in names:                       # порядок объявления = приоритет
            if rx.fullmatch(name):
                return name
    return names[0]


def run_candidate(candidate_code: str, task_dir: Path, work_dir: Path,
                  entry_patterns: list[str]) -> OneCRunResult:
    """Полный прогон одного кандидата B: сборка → база → исполнение → результат."""
    from .assemble import assemble_run_config

    entry = detect_entry_point(candidate_code, entry_patterns)
    if entry is None:
        return OneCRunResult(status="no_entry",
                             infra_detail="в коде кандидата не найдено ни одной функции")

    work_dir.mkdir(parents=True, exist_ok=True)

    # 1) пустая конфа-базис: выгружается платформой ОДИН раз на машину
    #    (общий кэш в work/), в work_dir кандидата попадает копией — иначе
    #    каждый кандидат платит ~50с за идентичную выгрузку.
    empty_cfg = work_dir / "empty-cfg"
    if not (empty_cfg / "Configuration.xml").exists():
        cache = _empty_cfg_cache()
        if cache is None:
            return OneCRunResult(status="infra_error", entry_point=entry,
                                 infra_detail="не удалось выгрузить пустую конфигурацию (кэш)")
        shutil.copytree(cache, empty_cfg, dirs_exist_ok=True)

    # 2) сборка прогонной конфы (на хосте, чистый Python)
    assemble_run_config(task_dir, candidate_code, entry,
                        empty_cfg, work_dir / "run-cfg")

    # 3) база + загрузка + прогон (один вызов контейнера, права чинятся внутри).
    # На шаге ENTERPRISE — свой timeout: битый кандидат может повесить клиент
    # модальным окном ошибки компиляции; зависание = чей-то дефект, режем за 90с,
    # причину различает _classify_no_result (CheckModules).
    script = (
        f"rm -rf /work/ib /work/result.txt; "
        f"xvfb-run-1c {ONEC_BIN} CREATEINFOBASE 'File=/work/ib;Locale=ru_RU;' >/dev/null 2>&1 && "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/LoadConfigFromFiles /work/run-cfg /Out /work/load.log >/dev/null 2>&1 && "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/UpdateDBCfg /Out /work/upd.log >/dev/null 2>&1 && "
        f"timeout 90 xvfb-run-1c {ONEC_BIN} ENTERPRISE /IBConnectionString 'File=/work/ib;' "
        f"/C ПрогонТеста >/dev/null 2>&1; "
        f"chmod -R a+rwX /work 2>/dev/null; true"
    )
    try:
        _in_container(work_dir, script, STEP_TIMEOUT_S * 3)
    except subprocess.TimeoutExpired:
        return _classify_no_result(work_dir, entry, context="таймаут прогона в контейнере")

    # 4) результат
    result_file = work_dir / "result.txt"
    if not result_file.exists():
        return _classify_no_result(work_dir, entry)

    return parse_result(result_file.read_text(encoding="utf-8-sig", errors="replace"), entry)


def _classify_no_result(work_dir: Path, entry: str | None,
                        context: str = "result.txt не создан") -> OneCRunResult:
    """Прогон не дал result.txt (или завис): вина кандидата или инфраструктуры?

    Различаем компиляцией: /CheckModules по загруженной конфе. Ошибки в модуле
    «КодКандидата» → candidate_error (балл 0 честен — некомпилирующийся кандидат
    не должен выпадать из Q как «не измеренный»; зависание клиента модальным
    окном ошибки компиляции — тот же случай). Иначе — no_result: похоже на
    инфраструктуру → None («не измерено»).
    """
    try:
        res = _in_container(work_dir, (
            f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
            f"/CheckModules -Server /Out /work/check.log >/dev/null 2>&1; "
            f"chmod a+r /work/check.log 2>/dev/null; cat /work/check.log 2>/dev/null"
        ), STEP_TIMEOUT_S)
        check_log = res.stdout
    except subprocess.TimeoutExpired:
        check_log = ""
    if "КодКандидата" in check_log:
        return OneCRunResult(status="candidate_error", entry_point=entry,
                             log=check_log[:500],
                             infra_detail=f"модуль кандидата не компилируется ({context})")
    load_log = (work_dir / "load.log").read_text(encoding="utf-8-sig", errors="replace") \
        if (work_dir / "load.log").exists() else ""
    return OneCRunResult(status="no_result", entry_point=entry,
                         infra_detail=f"{context}; check: {check_log[:200]}; "
                                      f"load.log: {load_log[:200]}")


def parse_result(text: str, entry: str | None = None) -> OneCRunResult:
    """Разбор "PASSED=n;TOTAL=m;<лог>" + классификация платформенных ошибок (сигнал P)."""
    text = text.strip()
    m = RESULT_RE.search(text)
    if not m:
        # обработчик упал до тестов (КЛИЕНТ_ИСКЛЮЧЕНИЕ и т.п.)
        markers = [p for p in PLATFORM_ERROR_MARKERS if p.lower() in text.lower()]
        return OneCRunResult(status="ok", passed=0, total=0, log=text[:500],
                             platform_errors=markers, entry_point=entry)
    log = m.group(3).strip()
    markers = [p for p in PLATFORM_ERROR_MARKERS if p.lower() in log.lower()]
    return OneCRunResult(status="ok", passed=int(m.group(1)), total=int(m.group(2)),
                         log=log[:500], platform_errors=markers,
                         platform_error_tests=_count_platform_error_tests(log),
                         entry_point=entry)


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
