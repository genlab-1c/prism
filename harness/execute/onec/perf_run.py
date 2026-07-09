"""Замер оси O ИСПОЛНЕНИЕМ для категории B — обращения кандидата к данным (техжурнал 1С).

Идея — близнец категории A: A растит массив и считает шаги кода; B растит БАЗУ и считает
ПОХОДЫ В СУБД. Решение набором даёт плоский счёт (O(1) запросов), «запрос в цикле» — растущий.

Как (проверено спайком, см. память cat-b-o-exec-techlog):
 1. база растится до размера N (scale_fixtures: +N элементов справочника под группой + движения);
 2. на СЕССИЮ ПрогонаЗамера включается техжурнал (logcfg.xml в /opt/1cv8t/conf — только этот
    процесс его прочитает), кандидат зовётся один раз замерочным вызовом (perf.call);
 3. события SDBL/DBV8DBEng парсятся; кандидату принадлежит событие, если в его Context есть
    «КодКандидата.Модуль» (стройка фикстур идёт под «Тесты.Модуль» и отсекается).
Счёт детерминирован (тот же код + та же база → то же число), как codestat в A.

Раннер — тот же образ prism-onec, что и корректностный прогон (оси M/P): образ один,
СЕАНС отдельный (лог включён, база больше, зовём замерочным вызовом, а не проверками).
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel

from harness.execute.onec.assemble import assemble_run_config
from harness.execute.onec.runner import DOCKER_IMAGE, _empty_cfg_cache, detect_entry_point

# logcfg: все события → /work/techlog. Включаем ТОЛЬКО перед сессией замера.
LOGCFG = """<?xml version="1.0"?>
<config xmlns="http://v8.1c.ru/v8/tech-log">
  <log location="/work/techlog" history="4">
    <event><ne property="Name" value=""/></event>
    <property name="All"/>
  </log>
</config>
"""

CAND_CONTEXT = "КодКандидата.Модуль"  # кадр стека = код кандидата (атрибуция обращений к данным)
_EVENT_HEAD = re.compile(r"^\d\d:\d\d\.\d+-\d+,([A-Za-z0-9]+),")
STEP_TIMEOUT_S = 180

# Замерочный харнесс: подменяет tests.bsl. Строит (растимую) базу и зовёт кандидата ОДИН раз
# замерочным вызовом perf.call. Возврат в формате раннера, чтобы прогон считался состоявшимся.
_PERF_HARNESS = """Функция ПрогнатьТест() Экспорт
\tСоздатьФикстуры();
\t{call};
\tВозврат "PASSED=1;TOTAL=1;perf";
КонецФункции
"""


class DbOpsResult(BaseModel):
    """Обращения кандидата к данным на одном размере базы."""

    size: int
    cand_sdbl: int = 0  # логических обращений к данным (SDBL) в контексте кандидата
    cand_dbeng: int = 0  # низкоуровневых обращений к движку файловой БД
    cand_reg_reads: int = 0  # чтений физтаблиц регистров (_AccumRg*/_InfoRg*/_AccRg*) кандидатом
    total_sdbl: int = 0  # всего SDBL в сессии (для диагностики шума)
    result: str = ""  # строка result.txt (маркер, что прогон состоялся)
    ok: bool = False
    note: str = ""


def _subst_unit(value, ref: str):
    """В шаблоне записи '$unit' → ссылка на синтетический элемент этой единицы i."""
    return ref if value == "$unit" else value


def scale_fixtures(fixtures: dict, n: int, grow: dict) -> dict:
    """Дописать в базу n синтетических «единиц» по спеке grow (композиция блоков).

    grow (все блоки опциональны, комбинируются; единицы связаны индексом i, ссылка на новый
    элемент справочника этой единицы = "$unit" в шаблонах записей):
      name_prefix: префикс ref/наименования новых элементов (по умолч. «Перф»)
      catalog:      {name, parent?, owner?, attrs?}         — элемент справочника
      accumulation: {register, registrar, record}           — движение регистра накопления
      information:  {register, record}                       — запись независимого РС
      accounting:   {register, registrar, record}            — проводка регистра бухгалтерии
    record — шаблон записи (ключ→значение как в fixtures.yaml); "$unit" подставляется новым элементом.
    """
    fx = copy.deepcopy(fixtures)
    prefix = grow.get("name_prefix", "Перф")
    for i in range(1, n + 1):
        ref = f"{prefix}{i}"
        cat = grow.get("catalog")
        if cat:
            item = {"ref": ref, "Наименование": f"{prefix} {i}"}
            if cat.get("parent"):
                item["parent"] = cat["parent"]
            if cat.get("owner"):
                item["owner"] = cat["owner"]
            for k, v in (cat.get("attrs") or {}).items():
                item[k] = _subst_unit(v, ref)
            fx.setdefault("catalogs", {}).setdefault(cat["name"], []).append(item)
        acc = grow.get("accumulation")
        if acc:
            block = fx.setdefault("register_records", {}).setdefault(acc["register"], {})
            block["registrar"] = acc["registrar"]
            block.setdefault("records", []).append(
                {k: _subst_unit(v, ref) for k, v in acc["record"].items()}
            )
        inf = grow.get("information")
        if inf:
            fx.setdefault("info_records", {}).setdefault(inf["register"], []).append(
                {k: _subst_unit(v, ref) for k, v in inf["record"].items()}
            )
        acn = grow.get("accounting")
        if acn:
            block = fx.setdefault("accounting_records", {}).setdefault(acn["register"], {})
            block["registrar"] = acn["registrar"]
            block.setdefault("records", []).append(
                {k: _subst_unit(v, ref) for k, v in acn["record"].items()}
            )
    return fx


def _synth_perf_task(task_dir: Path, perf: dict, n: int, dest: Path) -> Path:
    """Собрать временный каталог задачи для замера: config_spec (копия) + растимые фикстуры +
    tests.bsl, подменённый на замерочный харнесс с perf.call."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy(task_dir / "config_spec.yaml", dest / "config_spec.yaml")
    fixtures = yaml.safe_load((task_dir / "fixtures.yaml").read_text(encoding="utf-8"))
    grown = scale_fixtures(fixtures, n, perf["grow"])
    (dest / "fixtures.yaml").write_text(
        yaml.safe_dump(grown, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    harness = _PERF_HARNESS.format(
        call=perf["call"]
    )  # perf.call содержит {{ENTRY}} — заменит assemble
    (dest / "tests.bsl").write_text(harness, encoding="utf-8")
    return dest


def _run_container(work_dir: Path) -> None:
    """Собрать базу и прогнать сессию замера с включённым (только на неё) техжурналом."""
    script = r"""
BIN="$(ls /opt/1cv8t/x86_64/*/1cv8t 2>/dev/null | head -1)"
rm -rf /work/ib /work/result.txt /work/techlog; mkdir -p /work/techlog
xvfb-run-1c "$BIN" CREATEINFOBASE "File=/work/ib;Locale=ru_RU;" >/dev/null 2>&1
xvfb-run-1c "$BIN" DESIGNER /IBConnectionString "File=/work/ib;" /LoadConfigFromFiles /work/run-cfg /Out /work/load.log >/dev/null 2>&1
xvfb-run-1c "$BIN" DESIGNER /IBConnectionString "File=/work/ib;" /UpdateDBCfg /Out /work/upd.log >/dev/null 2>&1
cp /work/logcfg.xml /opt/1cv8t/conf/logcfg.xml
timeout 120 xvfb-run-1c "$BIN" ENTERPRISE /IBConnectionString "File=/work/ib;" /C ПрогонТеста >/dev/null 2>&1
sleep 2
chmod -R a+rwX /work 2>/dev/null; true
"""
    name = f"prism-operf-{uuid.uuid4().hex[:12]}"
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network=none",
                "-v",
                f"{work_dir}:/work",
                DOCKER_IMAGE,
                "bash",
                "-lc",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=STEP_TIMEOUT_S * 3,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        raise


def _iter_events(log_text: str):
    """Событие = строка-заголовок «время-длит,ИМЯ,…» + строки-продолжения (многострочный Context)."""
    name, block = None, []
    for line in log_text.splitlines():
        m = _EVENT_HEAD.match(line)
        if m:
            if name is not None:
                yield name, "\n".join(block)
            name, block = m.group(1), [line]
        else:
            block.append(line)
    if name is not None:
        yield name, "\n".join(block)


def _parse_db_ops(work_dir: Path, size: int) -> DbOpsResult:
    res = DbOpsResult(size=size)
    rf = work_dir / "result.txt"
    res.result = rf.read_text(encoding="utf-8-sig", errors="replace").strip() if rf.exists() else ""
    res.ok = "PASSED=" in res.result
    logs = list((work_dir / "techlog").rglob("*.log"))
    if not logs:
        res.note = "техжурнал пуст"
        return res
    reg_re = re.compile(r"FROM\s+(_AccumRg\w*|_InfoRg\w*|_AccRg\w*|_AccntRg\w*)")
    for lf in logs:
        for name, block in _iter_events(lf.read_text(encoding="utf-8-sig", errors="replace")):
            if name == "SDBL":
                res.total_sdbl += 1
            if CAND_CONTEXT in block:
                if name == "SDBL":
                    res.cand_sdbl += 1
                elif name == "DBV8DBEng":
                    res.cand_dbeng += 1
                    res.cand_reg_reads += len(reg_re.findall(block))
    return res


def measure_db_ops(
    candidate_code: str,
    task_dir: Path,
    perf: dict,
    n: int,
    work_dir: Path,
    entry_patterns: list[str],
) -> DbOpsResult:
    """Замерить обращения кандидата к данным на базе размера n (техжурнал + атрибуция по Context)."""
    entry = detect_entry_point(candidate_code, entry_patterns)
    if entry is None:
        return DbOpsResult(size=n, note="в коде кандидата нет функции")
    work_dir.mkdir(parents=True, exist_ok=True)
    empty = work_dir / "empty-cfg"
    cache = _empty_cfg_cache()
    if cache is None:
        return DbOpsResult(size=n, note="нет пустой конфы")
    shutil.copytree(cache, empty, dirs_exist_ok=True)
    synth = _synth_perf_task(task_dir, perf, n, work_dir / "perf-task")
    assemble_run_config(
        synth, candidate_code, entry, empty, work_dir / "run-cfg", result_path="/work/result.txt"
    )
    (work_dir / "logcfg.xml").write_text(LOGCFG, encoding="utf-8")
    _run_container(work_dir)
    return _parse_db_ops(work_dir, n)
