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
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from harness.execute import measure_cache

DOCKER_IMAGE = "prism-onec:latest"
# Путь к бинарю учебного клиента — версия НЕ зашита: находим его глобом в рантайме внутри
# контейнера (подставляется в bash -c). Работает с образом любой версии 1С и не зависит от
# PATH (в части старых образов PATH к бинарю битый).
ONEC_BIN = '"$(ls /opt/1cv8t/x86_64/*/1cv8t 2>/dev/null | head -1)"'
STEP_TIMEOUT_S = 180  # на каждый шаг конфигуратора (DESIGNER) или клиента 1С
RESULT_RE = re.compile(r"PASSED=(\d+);TOTAL=(\d+);?(.*)", re.DOTALL)

# Сколько символов лога теста кладём в запись прогона. Классификация идёт по ПОЛНОМУ
# логу (обрезка ниже по течению), но аудит читает сохранённое, и на 500 символах
# сообщения рвались на полуслове («Синтаксическа», «Поле не») — балл P по данным
# перепроверить было нельзя.
LOG_LIMIT = 4000

# Версия СМЫСЛА корректностного прогона: поднимать, когда меняется состав сохраняемых
# артефактов или скрипт контейнера. Сам скрипт в ключ не хешится — он длинный и правится
# по мелочам, а вот его СУТЬ (что мы измеряем) версионируется здесь.
RUN_CACHE_VERSION = "2"  # 2: к прогону добавлен техжурнал — отметка «кандидат ходил в базу»

# Техжурнал корректностного прогона. Узкий, в отличие от замерочного (там property All):
# нужен ровно один факт — обращался ли КОД КАНДИДАТА к данным. Событий два, свойство одно,
# поэтому лог остаётся крошечным и прогон почти не замедляется.
#
# Зачем. Ось P судит о знании метаданных по тому, как упали тесты. Но тест, упавший на общем
# BSL («Слишком много фактических параметров», «Тип не определен»), до базы, скорее всего,
# вовсе не дошёл — и свидетельства о метаданных не дал, хотя считался «чистым». На корпусе
# это 36 записей с P=10 при полностью провалившихся тестах. Техжурнал отвечает на вопрос
# прямо: было ли хоть одно обращение к данным из кода кандидата.
RUN_LOGCFG = """<?xml version="1.0"?>
<config xmlns="http://v8.1c.ru/v8/tech-log">
  <log location="/work/techlog" history="1">
    <event><eq property="Name" value="SDBL"/></event>
    <property name="Context"/>
  </log>
</config>
"""
CAND_CONTEXT = "КодКандидата.Модуль"  # кадр стека = код кандидата


@lru_cache(maxsize=1)
def platform_subclasses() -> tuple[dict, ...]:
    """Подклассы платформенной ошибки: к какой оси она на самом деле относится.

    Маркер говорит «сломалось при обращении к платформе», но не говорит ЧТО. Под общим
    «Ошибка при вызове метода контекста (Выполнить)» лежат две разные вещи: обращение к
    несуществующему полю или таблице (это знание метаданных, ось P) и кривой текст запроса
    (это авторство кода, по конституции ось M). Считать второе провалом P значит наказывать
    дважды: запрос не выполнился → тест провалился → M уже упала.
    Порядок правил важен: частное выше общего.
    """
    from harness.loaders import load_error_taxonomy

    return tuple(load_error_taxonomy().get("platform_subclasses") or [])


def platform_verdict(segment: str) -> str:
    """Что этот тест сказал про знание метаданных: "fault" | "clean" | "unverified".

    fault      — упал на обращении к метаданным (ось P наказывается);
    unverified — упал ДО того, как платформа дошла до имён (запрос не разобрался
                 грамматически): свидетельства нет ни за, ни против;
    clean      — всё остальное, включая неверный ответ и общие ошибки BSL: обращения
                 к метаданным состоялись, значит ось P их подтверждает.

    Различие fault/unverified существует, чтобы не заменить одну неправду другой.
    Просто перестать считать кривой запрос провалом P мало: тест тогда попадёт в
    ЧИСЛИТЕЛЬ чистых, и запись получит P=10 «все обращения к метаданным отработали»,
    хотя ни одного обращения не проверялось. На корпусе это ровно 6 записей, прыгающих
    с 0 на 10. Честно — выбросить такой тест из знаменателя.
    """
    low = segment.lower()
    if not any(p.lower() in low for p in platform_error_markers()):
        return "clean"
    for rule in platform_subclasses():
        if any(m in segment for m in rule.get("match") or []):
            if rule.get("axis") == "P":
                return "fault"
            return "clean" if rule.get("metadata_reached", True) else "unverified"
    return "fault"  # маркер сработал, класс неизвестен — см. «не опознано» в prism audit


@lru_cache(maxsize=1)
def platform_error_markers() -> tuple[str, ...]:
    """Маркеры платформенной ошибки в логе теста — сигнал оси P (обращение к метаданным),
    в отличие от просто неверного ответа (это ось M).

    Список живёт в metrics/error_taxonomy.yaml: пороги и словари — данные, не код.
    """
    from harness.loaders import load_error_taxonomy

    markers = load_error_taxonomy().get("platform_error_markers") or []
    if not markers:
        raise ValueError(
            "metrics/error_taxonomy.yaml: пустой platform_error_markers — "
            "без маркеров ось P объявит чистыми все тесты подряд"
        )
    return tuple(markers)


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
    # Ключ сырья в хранилище замеров (results/.measure_cache). По нему любая запись
    # оценок разворачивается обратно в артефакты прогона: check.log, result.txt, коды
    # завершения. Без него сырьё приходилось воспроизводить новым прогоном 1С.
    run_key: str = ""
    # Обращался ли КОД КАНДИДАТА к данным хоть раз за сеанс (по техжурналу, события SDBL
    # с «КодКандидата.Модуль» в Context). None = техжурнала нет (старая запись кэша или
    # сеанс не стартовал). Ось P без этого не отличает «метаданные в порядке» от «до базы
    # не дошли»: см. RUN_LOGCFG.
    db_touched: bool | None = None
    # Тесты, не давшие свидетельства об именах метаданных: запрос не разобрался
    # грамматически, до проверки имён платформа не дошла. Не «чисто» и не «провал» —
    # выбрасываются из знаменателя доли оси P (см. platform_verdict).
    unverified_tests: int = 0
    compile_error_lines: list[int] = []  # строки ошибок компиляции модуля кандидата (ось S)
    compile_errors: list[str] = []  # тексты ошибок компилятора (диагностика)
    entry_point: str | None = None
    infra_detail: str = ""  # диагностика инфраструктурных падений
    # Аварийный код завершения /CheckModules (139 = сегфолт). Компилятор платформы падает на
    # некоторых модулях кандидатов и не пишет ни байта в лог; без кода это неотличимо от
    # «ошибок нет». Наблюдалось на `Вызвать Исключение` двумя словами (1С 8.3.27).
    compiler_exit: int | None = None


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


# Имя-заглушка для сборки, когда точки входа нет: тестам нужно ЧТО-ТО подставить вместо
# {{ENTRY}}, иначе модуль Тесты не компилируется. Сам кандидат от этого не меняется.
ENTRY_PLACEHOLDER = "ТочкаВходаНеНайдена"

# Английские ключевые слова BSL принимает наравне с русскими, и модели их пишут: модуль с
# `function ИмяФункции(...) Экспорт` компилируется без замечаний. Детектор, знавший только
# русские слова, такую рабочую функцию не находил — прогон падал в no_entry, M и P в ноль.
SUB_RE = re.compile(
    r"^\s*(?:Функция|Процедура|Function|Procedure)\s+([\wа-яА-ЯёЁ]+)\s*\(",
    re.MULTILINE | re.IGNORECASE,
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
    # Точки входа нет — прогон НЕ отменяем: компилятор 1С должен высказаться о модуле.
    # Раньше здесь стоял возврат до контейнера, и ось S выводилась из пустого списка
    # ошибок — «компилируется без ошибок» про модуль, которого компилятор не видел.
    # Тесты при этом звать нечего, поэтому ENTERPRISE ниже пропускается: иначе сломанный
    # модуль Тесты не создаст result.txt и вина кандидата станет «инфраструктурой».
    work_dir.mkdir(parents=True, exist_ok=True)

    # Прогон 1С — самая дорогая операция бенчмарка (поднимается информационная база).
    # Его ВХОД — код кандидата плюс файлы задачи; правка протокола или скорера вход не меняет,
    # поэтому сырьё прогона (логи и result.txt) берём из кэша, а балл выводим заново.
    ckey = _run_key(candidate_code, task_dir, entry)
    cached = measure_cache.get(ckey) if ckey else None
    if cached is not None:
        for name, text in (
            ("check.log", cached.get("check", "")),
            ("result.txt", cached.get("result", "")),
            ("load.log", cached.get("load", "")),
            ("check.rc", cached.get("check_rc", "")),
            ("enterprise.rc", cached.get("ent_rc", "")),
        ):
            (work_dir / name).write_text(text, encoding="utf-8")
        out = _verdict(work_dir, entry, timed_out=False, db_touched=cached.get("db"))
        out.run_key = ckey or ""
        return out

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
    assemble_run_config(
        task_dir, candidate_code, entry or ENTRY_PLACEHOLDER, empty_cfg, work_dir / "run-cfg"
    )

    # 3) база + компиляция (S) + исполнение (M/P) — один вызов контейнера.
    # /CheckModules даёт ось S (ошибки модуля КодКандидата); если кандидат не
    # компилируется — ENTERPRISE не запускаем (быстрее и честно: M/P = 0).
    # На ENTERPRISE свой timeout 90: чужой дефект не должен висеть.
    # CheckModules проверяет конфигурацию БД → строго ПОСЛЕ UpdateDBCfg; оба
    # безусловно после успешного load (через ;), чтобы ошибки кандидата всплыли,
    # даже если UpdateDBCfg споткнулся. ENTERPRISE — только при чистой компиляции.
    (work_dir / "logcfg.xml").write_text(RUN_LOGCFG, encoding="utf-8")
    script = (
        f"rm -rf /work/ib /work/result.txt /work/check.log /work/check.rc /work/enterprise.rc "
        f"/work/techlog; mkdir -p /work/techlog; "
        f"xvfb-run-1c {ONEC_BIN} CREATEINFOBASE 'File=/work/ib;Locale=ru_RU;' >/dev/null 2>&1 && "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/LoadConfigFromFiles /work/run-cfg /Out /work/load.log >/dev/null 2>&1 && {{ "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/UpdateDBCfg /Out /work/upd.log >/dev/null 2>&1; "
        f"xvfb-run-1c {ONEC_BIN} DESIGNER /IBConnectionString 'File=/work/ib;' "
        f"/CheckModules -Server /Out /work/check.log >/dev/null 2>&1; echo $? > /work/check.rc; "
        + (
            f"if grep -q 'КодКандидата' /work/check.log 2>/dev/null; then true; else "
            # Техжурнал включаем ТОЛЬКО на сеанс тестов: конфигуратор нам не интересен,
            # а logcfg действует на весь процесс платформы.
            f"cp /work/logcfg.xml /opt/1cv8t/conf/logcfg.xml 2>/dev/null; "
            f"timeout 90 xvfb-run-1c {ONEC_BIN} ENTERPRISE /IBConnectionString 'File=/work/ib;' "
            f"/C ПрогонТеста >/dev/null 2>&1; echo $? > /work/enterprise.rc; "
            f"sleep 2; rm -f /opt/1cv8t/conf/logcfg.xml 2>/dev/null; fi; "
            if entry is not None
            else ""
        )
        + "}; chmod -R a+rwX /work 2>/dev/null; true"
    )
    timed_out = False
    try:
        _in_container(work_dir, script, STEP_TIMEOUT_S * 3)
    except subprocess.TimeoutExpired:
        timed_out = True

    res = _verdict(work_dir, entry, timed_out)
    res.run_key = ckey or ""
    if ckey and not timed_out:  # таймаут — свойство машины, его не кэшируем
        measure_cache.put(
            ckey,
            {
                "check": _read(work_dir / "check.log"),
                "result": _read(work_dir / "result.txt"),
                "load": _read(work_dir / "load.log")[:2000],
                "check_rc": _read(work_dir / "check.rc"),
                "ent_rc": _read(work_dir / "enterprise.rc"),
                # Не сам техжурнал (он большой и нужен ровно одним фактом), а вывод из него.
                "db": _db_touched(work_dir),
            },
        )
    return res


def _run_key(candidate_code: str, task_dir: Path, entry: str | None) -> str | None:
    """Ключ прогона: код кандидата + файлы задачи + точка входа + версия платформы и сборки.

    Логика сборки конфигурации входит в ключ своим исходником: поменяли assemble.py — ключ
    другой, кэш инвалидируется сам, без ручного версионирования.
    """
    try:
        parts = [RUN_CACHE_VERSION, candidate_code, entry or "", DOCKER_IMAGE]
        for name in ("config_spec.yaml", "fixtures.yaml", "tests.bsl"):
            parts.append(_read(task_dir / name))
        parts.append((Path(__file__).parent / "assemble.py").read_text(encoding="utf-8"))
        return measure_cache.key("onec_run", *parts)
    except OSError:
        return None


def _verdict(
    work_dir: Path, entry: str | None, timed_out: bool, db_touched: bool | None = None
) -> OneCRunResult:
    """Разобрать артефакты прогона в вердикт. Один путь и для живого прогона, и для кэша.

    db_touched передаётся из кэша; при живом прогоне выводится из техжурнала здесь же.
    """
    if db_touched is None:
        db_touched = _db_touched(work_dir)
    # ось S — ошибки компиляции модуля кандидата (компилятор 1С, не статика)
    lines, errors = _parse_compile_log(_read(work_dir / "check.log"))
    check_rc = _read_rc(work_dir / "check.rc")
    if not lines and check_rc:  # компилятор упал молча: лог пуст, код аварийный
        msg = f"компилятор платформы аварийно завершился (код {check_rc}) — модуль не принят"
        return OneCRunResult(
            status="candidate_error",
            entry_point=entry,
            compile_errors=[msg],
            compiler_exit=check_rc,
            log=msg,
            infra_detail="модуль кандидата роняет компилятор платформы",
        )
    if lines:  # не компилируется → вина кандидата
        return OneCRunResult(
            status="candidate_error",
            entry_point=entry,
            compile_error_lines=lines,
            compile_errors=errors,
            log="; ".join(errors[:3])[:500],
            infra_detail="модуль кандидата не компилируется",
        )

    if entry is None:  # модуль собрался, но звать нечего → вина кандидата, оси M и P = 0
        return OneCRunResult(
            status="no_entry", infra_detail="в коде кандидата не найдено ни одной функции"
        )

    # компилируется → M/P из result.txt
    result_file = work_dir / "result.txt"
    if result_file.exists():
        res = parse_result(result_file.read_text(encoding="utf-8-sig", errors="replace"), entry)
        res.db_touched = db_touched  # факт из техжурнала: добрался ли код до данных
        return res

    detail = "таймаут прогона" if timed_out else "result.txt не создан"
    ent_rc = _read_rc(work_dir / "enterprise.rc")
    if ent_rc:
        detail += f"; сеанс 1С завершился с кодом {ent_rc}"
    return OneCRunResult(
        status="no_result",
        entry_point=entry,
        infra_detail=f"{detail}; load.log: {_read(work_dir / 'load.log')[:200]}",
    )


def _read_rc(path: Path) -> int | None:
    """Код завершения шага из файла, который пишет скрипт контейнера. Нет файла / мусор → None."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


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


def _db_touched(work_dir: Path) -> bool | None:
    """Ходил ли КОД КАНДИДАТА в базу за сеанс тестов (по техжурналу).

    True  — есть событие SDBL, в Context которого кадр «КодКандидата.Модуль»;
    False — техжурнал есть, таких событий нет: код до данных не добрался;
    None  — техжурнала нет вовсе (сеанс не стартовал либо запись из старого кэша),
            отличать «нет обращений» от «не знаем» обязательно, иначе ось P
            объявит непроверенным то, что просто не записалось.

    Читаем построчно и выходим на первом совпадении: лог узкий, но на больших базах
    всё равно бывает в мегабайтах, а нужен один факт.
    """
    logs = list((work_dir / "techlog").rglob("*.log")) if (work_dir / "techlog").exists() else []
    if not logs:
        return None
    for path in logs:
        try:
            with path.open(encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    if CAND_CONTEXT in line:
                        return True
        except OSError:
            return None
    return False


def _parse_compile_log(text: str) -> tuple[list[int], list[str]]:
    """Из лога /CheckModules → (строки ошибок модуля кандидата, тексты ошибок)."""
    lines, errors = [], []
    for m in _COMPILE_RE.finditer(text or ""):
        lines.append(int(m.group(1)))
        errors.append(m.group(2).strip())
    return lines, errors


def parse_result(text: str, entry: str | None = None) -> OneCRunResult:
    """Разбор "PASSED=n;TOTAL=m;<лог>" + классификация платформенных ошибок (сигнал P)."""
    text = text.strip()
    m = RESULT_RE.search(text)
    if not m:
        # обработчик упал до тестов (КЛИЕНТ_ИСКЛЮЧЕНИЕ и т.п.)
        markers = [p for p in platform_error_markers() if p.lower() in text.lower()]
        return OneCRunResult(
            status="ok",
            passed=0,
            total=0,
            log=text[:LOG_LIMIT],
            platform_errors=markers,
            entry_point=entry,
        )
    log = m.group(3).strip()
    markers = [p for p in platform_error_markers() if p.lower() in log.lower()]
    faults, unverified = _count_verdicts(log)
    return OneCRunResult(
        status="ok",
        passed=int(m.group(1)),
        total=int(m.group(2)),
        log=log[:LOG_LIMIT],
        platform_errors=markers,
        platform_error_tests=faults,
        unverified_tests=unverified,
        entry_point=entry,
    )


def _count_platform_error_tests(log: str) -> int:
    """Сколько тестов упало платформенной ошибкой (сигнал P — clean/total).

    Лог формата «тестN ИСКЛЮЧЕНИЕ: …; тестM FAIL …»: режем по началам записей
    «тестN » и решаем по каждому сегменту (см. platform_fault). FAIL по значению (неверный
    ответ) платформенной ошибкой не считается — это территория оси M. Туда же уходит
    кривой текст запроса: он про авторство кода, а не про знание метаданных.

    Слово ИСКЛЮЧЕНИЕ при этом не требуется, и вот почему. Часть tasks/*/tests.bsl
    ловит исключение сама и пишет его текстом внутрь «тестN FAIL (…)». Балл P тогда
    зависел от того, как оформлен тест, а не от того, что сделала модель: на B5
    три теста упали на одной платформенной ошибке, а P выходил 3.3 вместо 0.
    Решает не слово ИСКЛЮЧЕНИЕ, а наличие маркера — простой FAIL его не содержит.
    """
    return _count_verdicts(log)[0]


def _count_verdicts(log: str) -> tuple[int, int]:
    """(тестов с провалом по метаданным, тестов без свидетельства) по логу прогона."""
    fault = unverified = 0
    for seg in re.split(r"(?=тест\d+\s)", log):
        if not re.match(r"тест\d+\s", seg):
            continue
        verdict = platform_verdict(seg)
        fault += verdict == "fault"
        unverified += verdict == "unverified"
    return fault, unverified
