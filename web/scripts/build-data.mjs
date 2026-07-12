/* ============================================================
   PRISM web — сборка данных лидерборда + генераций.
   Источник правды — results/ бенчмарка. Здесь только проекция:
     · results/auto/*_auto_l1.json    → оценки S/M/O/P/Q
     · results/experiment_*.json      → код, который писали модели
     · generation/{models,pricing}.yaml → имя, вендор, цена
   На выходе (всё статическое, бэкенда нет):
     · src/data/leaderboard.json          — таблица (грузится сразу)
     · public/data/gen/<model>.json       — код по задачам (ленивая подгрузка)
   Код подсвечивается Shiki на БИЛДЕ (grammar BSL ниже) — на клиенте Shiki нет.
   ============================================================ */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';
import { createHighlighter } from 'shiki';

const HERE = path.dirname(fileURLToPath(import.meta.url)); // web/scripts
const REPO = path.resolve(HERE, '..', '..'); // корень prism/
const AUTO = path.join(REPO, 'results', 'auto');
const RESULTS = path.join(REPO, 'results');
const WEB = path.join(HERE, '..');

const readJSON = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const readYAML = (p) => yaml.load(fs.readFileSync(p, 'utf8'));

// --- каталог моделей (имя → id, вендор) и цены (id → тариф)
const catalog = readYAML(path.join(REPO, 'generation', 'models.yaml')).models;
const byName = {};
for (const m of Object.values(catalog)) byName[m.name] = { id: m.id, vendor: m.vendor };
const pricing = readYAML(path.join(REPO, 'generation', 'pricing.yaml')).prices || {};

const VENDOR = {
  anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google', deepseek: 'DeepSeek',
  alibaba: 'Alibaba', zhipu: 'Zhipu', yandex: 'Yandex', sber: 'Sber',
  xai: 'xAI', xiaomi: 'Xiaomi', minimax: 'MiniMax', moonshot: 'Moonshot', meta: 'Meta', mistral: 'Mistral',
};
// незнакомый вендор — хотя бы с заглавной, а не сырой id вроде «xai»
const vendorName = (v) => VENDOR[v] || (v ? v[0].toUpperCase() + v.slice(1) : '');

const findFile = (dir, prefix, suffix) =>
  fs.readdirSync(dir).find((f) => f.startsWith(prefix) && f.endsWith(suffix));
const autoFile = (cat) => findFile(AUTO, `experiment_${cat}_`, '_auto_l1.json');
const expFile = (cat) => findFile(RESULTS, `experiment_${cat}_`, '.json');

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const r1 = (v) => (v == null ? null : Math.round(v * 10) / 10);
const r2 = (v) => (v == null ? null : Math.round(v * 100) / 100);
// класс роста как настоящая формула: N в степени p, надстрочными знаками (юникод —
// чтобы читалось и в тексте, и в SVG-экспорте). 1.0 → N¹, 1.5 → N¹·⁵, 0 → N⁰.
const SUP = { 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹', '.': '·', '-': '⁻' };
const powN = (p) => (p == null ? '' : 'N' + [...String(p)].map((c) => SUP[c] ?? c).join(''));
// формула для показа: округляем до 0.1 и зажимаем отрицательную степень к N⁰ (небольшой минус —
// это шум замера на плоском/оптимальном решении, «операции не растут», а не «убывают»).
const growF = (v) => powN(v == null ? null : Math.max(0, r1(v)));
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const taskNum = (id) => parseInt(String(id).replace(/\D/g, ''), 10) || 0;

// B-задачи с нагрузочным замером O (есть perf.yaml) — у них O мерится ИСПОЛНЕНИЕМ,
// а не статикой; вердикт по O формулируется иначе.
const PERF_B = new Set(
  fs.readdirSync(path.join(REPO, 'tasks', 'category_b'))
    .filter((d) => fs.existsSync(path.join(REPO, 'tasks', 'category_b', d, 'perf.yaml')))
    .map((d) => d.split('_')[0]),
);
// коды perf/арх-антипаттернов BSL LS → человеческое имя (для оси O статикой)
const ANTI = {
  CreateQueryInCycle: 'запрос в цикле', VirtualTableCallWithoutParameters: 'ВТ без параметров',
  JoinWithVirtualTable: 'соединение с виртуальной таблицей', JoinWithSubQuery: 'соединение с подзапросом',
  QueryNestedFieldsByDot: 'поля через точку в запросе', SelectTopWithoutOrderBy: 'ПЕРВЫЕ без сортировки',
  LogicalOrInTheWhereSectionOfQuery: 'ИЛИ в условии ГДЕ', RefOveruse: 'лишние обращения .Ссылка',
  DeprecatedCurrentDate: 'устаревший ТекущаяДата',
};
const plural = (n, a, b, c) => {
  const nn = Math.abs(n) % 100, n1 = nn % 10;
  if (nn > 10 && nn < 20) return c;
  if (n1 > 1 && n1 < 5) return b;
  if (n1 === 1) return a;
  return c;
};

/* ---- 1. Оценки: агрегат по модели + срез по (модель, задача) ----
   Средние по задачам = те же числа, что `prism leaderboard`. */
function loadAuto(cat) {
  const auto = readJSON(path.join(AUTO, autoFile(cat)));
  const agg = {};
  const perTask = {}; // name → taskId → {scores, detail}
  for (const t of auto.tasks) {
    const a = (agg[t.model_name] ||= { id: t.model_id, S: [], M: [], O: [], P: [], Q: [], tasks: new Set() });
    a.tasks.add(t.task_id);
    const run = t.runs[0] || {};
    const scores = run.scores || {};
    (perTask[t.model_name] ||= {})[t.task_id] = { scores, detail: run.detail || {} };
    for (const ax of ['S', 'M', 'O', 'P', 'Q']) if (scores[ax] != null) a[ax].push(scores[ax]);
  }
  // Ось O имеет смысл, только если измерена на ДОСТАТОЧНОМ числе задач. Слабая модель может решить
  // 2 тривиальные задачи оптимально → её «O=10» стоит на 2 ячейках и вводит в заблуждение. Требуем
  // минимум задач с измеренным O, иначе агрегат O = N/A (оптимальность не оцениваем — мало решённого).
  const MIN_O_TASKS = 3;
  const summary = {};
  for (const [name, a] of Object.entries(agg)) {
    summary[name] = {
      id: a.id, taskCount: a.tasks.size,
      S: mean(a.S), M: mean(a.M),
      O: a.O.length >= MIN_O_TASKS ? mean(a.O) : null,
      P: mean(a.P), Q: mean(a.Q),
    };
  }
  return { exp: auto.experiment_id, summary, perTask };
}

const A = loadAuto('A');
const B = loadAuto('B');

/* ---- 2. Код: код, который писали модели (из рулона эксперимента) ---- */
function extractCode(resp) {
  if (!resp) return '';
  // язык-тег фенса может быть любым, включая кириллический «1с» — берём всё до конца строки
  const m = resp.match(/```[^\n]*\r?\n([\s\S]*?)```/);
  return (m ? m[1] : resp).trim();
}
function loadExperiment(cat) {
  const d = readJSON(path.join(RESULTS, expFile(cat)));
  const byModel = {}; // name → [{taskId, taskName, code}]
  for (const t of d.task_results) {
    const code = extractCode(t.runs[0]?.response);
    (byModel[t.model_name] ||= []).push({
      taskId: t.task_id,
      taskName: t.task_name,
      code,
      meta: {
        tokens: t.total_tokens || 0,
        tokensOut: t.runs?.[0]?.tokens_output || 0, // нужно для честной (по выходу) стоимости прогона
        cost: t.total_cost || 0,
        time: t.avg_time || 0,
        contextLoaded: !!t.context_loaded,
        contextObjects: (t.context_objects || []).map(String),
      },
    });
  }
  return byModel;
}
const expA = loadExperiment('A');
const expB = loadExperiment('B');

/* ---- 3. Подсветка BSL (Shiki, на билде). Компактная грамматика: ---- */
const BSL_GRAMMAR = {
  name: 'bsl',
  scopeName: 'source.bsl',
  patterns: [
    { name: 'comment.line.double-slash.bsl', match: '//.*$' },
    { name: 'string.quoted.double.bsl', begin: '"', end: '"', patterns: [{ match: '""' }] },
    { name: 'constant.other.date.bsl', match: "'[^']*'" },
    { name: 'keyword.preprocessor.bsl', match: '(?i)(^\\s*#\\s*\\S+|&[A-Za-zА-Яа-яЁё]+)' },
    { name: 'constant.language.bsl', match: '(?i)(?<![\\p{L}\\d_])(Истина|Ложь|Неопределено|True|False|Undefined|NULL)(?![\\p{L}\\d_])' },
    { name: 'keyword.control.bsl', match: '(?i)(?<![\\p{L}\\d_])(Если|Тогда|ИначеЕсли|Иначе|КонецЕсли|Для|Каждого|Из|По|Цикл|КонецЦикла|Пока|Функция|КонецФункции|Процедура|КонецПроцедуры|Возврат|Перем|Новый|Прервать|Продолжить|Попытка|Исключение|КонецПопытки|ВызватьИсключение|Экспорт|Знач|If|Then|ElsIf|Else|EndIf|For|Each|In|To|Do|EndDo|While|Function|EndFunction|Procedure|EndProcedure|Return|Var|New|Break|Continue|Try|Except|EndTry|Raise|Export|Val)(?![\\p{L}\\d_])' },
    { name: 'keyword.operator.word.bsl', match: '(?i)(?<![\\p{L}\\d_])(И|Или|Не|And|Or|Not)(?![\\p{L}\\d_])' },
    { name: 'constant.numeric.bsl', match: '(?<![\\p{L}_])\\d+(?:\\.\\d+)?' },
  ],
};

const hl = await createHighlighter({ themes: ['github-dark', 'github-light'], langs: [BSL_GRAMMAR, 'yaml'] });
const highlightAs = (code, lang) =>
  code ? hl.codeToHtml(code, { lang, themes: { dark: 'github-dark', light: 'github-light' }, defaultColor: false }) : '';
const highlight = (code) => highlightAs(code, 'bsl');

/* ---- 4. Сборка моделей для таблицы ---- */
const RUB = 85; // курс для отображения (как в pricing.yaml)
const costOf = (id) => {
  const p = pricing[id];
  if (!p) return '—';
  return `${Math.round(((p.input + p.output) / 2) * RUB)} ₽/1M`; // средняя цена за 1 млн токенов
};

/* Экономика прогона по модели: суммарные токены, ср. время на задачу и стоимость
   ВСЕГО прогона (A+B). Стоимость считаем по тарифу × фактическим токенам с разделением
   вход/выход — иначе модели с дорогим выходом (reasoning) выглядели бы дешевле, чем есть.
   Стоимость в результатах прогона храним как ОЦЕНКУ (pricing.yaml — снимок тарифов). */
function econOf(name, id) {
  const tasks = [...(expA[name] || []), ...(expB[name] || [])];
  if (!tasks.length) return {};
  let tokIn = 0, tokOut = 0, tokTot = 0, timeSum = 0, n = 0;
  for (const t of tasks) {
    const m = t.meta || {};
    tokTot += m.tokens || 0;
    tokOut += m.tokensOut || 0;
    tokIn += Math.max(0, (m.tokens || 0) - (m.tokensOut || 0));
    if (m.time) { timeSum += m.time; n += 1; }
  }
  const p = pricing[id];
  const runCost = p ? (tokIn * p.input + tokOut * p.output) / 1e6 : null;
  const genCount = tasks.length; // число генераций (задач A+B) в прогоне модели
  return {
    runCost: runCost == null ? null : Math.round(runCost * 1000) / 1000,
    // цена ОДНОЙ генерации = стоимость полного прогона ÷ число генераций (понятнее юзеру, чем «прогон»)
    genCost: runCost == null ? null : Math.round((runCost / genCount) * 1e5) / 1e5,
    genCount,
    priceIn: p ? p.input : null,
    priceOut: p ? p.output : null,
    tokensOut: tokOut,
    tokensTotal: tokTot,
    // токенов на одну генерацию (вход+выход) — метрика экономичности, НЕ зависит от тарифа
    tokPerGen: genCount ? Math.round(tokTot / genCount) : null,
    avgTime: n ? Math.round((timeSum / n) * 10) / 10 : null,
  };
}

const names = new Set([...Object.keys(A.summary), ...Object.keys(B.summary)]);
const models = [...names].map((name) => {
  const a = A.summary[name];
  const b = B.summary[name];
  const meta = byName[name] || {};
  // общий Q — среднее по A и B со взвешиванием на число задач (как в сводном зачёте)
  const wA = a ? a.taskCount : 0, wB = b ? b.taskCount : 0;
  const qOverall = (wA + wB) ? r2(((a?.Q || 0) * wA + (b?.Q || 0) * wB) / (wA + wB)) : null;
  return {
    id: slug(name),
    name,
    vendor: meta.vendor || '',
    family: vendorName(meta.vendor),
    cost: costOf(meta.id),
    econ: econOf(name, meta.id),
    A: a ? { S: r1(a.S), M: r1(a.M), O: r1(a.O) } : null,
    B: b ? { S: r1(b.S), M: r1(b.M), O: r1(b.O), P: r1(b.P) } : null,
    qA: a ? r2(a.Q) : null,
    qB: b ? r2(b.Q) : null,
    qOverall,
    verified: false,
  };
});

/* ---- 4b. Обогащаем виды лидерборда из site_data.json (эмитит `prism docs`) ----
   Те же расчёты, что в CLI: ± погрешность, доля решённых, воронка исходов,
   срез по навыкам (M) / платформе (P). Нет файла → только overall (выше). */
let profileCols = { A: [], B: [] };
let tagLabels = {};
const sdPath = path.join(AUTO, 'site_data.json');
if (fs.existsSync(sdPath)) {
  const sd = readJSON(sdPath);
  profileCols = sd.profileCols || profileCols;
  tagLabels = sd.tagLabels || {};
  const sdByName = Object.fromEntries(sd.models.map((m) => [m.name, m]));
  for (const m of models) {
    const s = sdByName[m.name];
    if (!s) continue;
    for (const cat of ['A', 'B']) {
      if (m[cat] && s[cat]) {
        m[cat].margin = s[cat].margin == null ? null : r1(s[cat].margin);
        m[cat].solved = s[cat].solved;
        m[cat].funnel = s[cat].funnel;
        m[cat].profile = s[cat].profile;
      }
    }
  }
} else {
  console.warn('  ! results/auto/site_data.json не найден — запусти `prism docs` для funnel/profile');
}

/* ---- 5. Per-model файлы генераций (ленивая подгрузка по клику) ---- */
// Каталог НЕ сносим целиком (иначе работающий dev-сервер Vite теряет его из виду и
// отдаёт 404 на свежие файлы) — обновляем на месте, лишние подчищаем после записи.
const GEN_DIR = path.join(WEB, 'public', 'data', 'gen');
fs.mkdirSync(GEN_DIR, { recursive: true });

const pick = (s) => (s == null ? null : r1(s)); // оси задачи — к одному знаку

/* Ошибки компиляции с МЕСТОМ (строка) и текстом. A: из OneScript (M.errors —
   «Error in line 7,21 / Expecting symbol: Equal»); B: компилятор 1С (M.compile_errors +
   строки M.compile_error_lines). Возвращает «строка N · текст», человекочитаемо. */
// Перевод частых сообщений компилятора (OneScript — по-английски) на человеческий русский.
const SYM = {
  Equal: '«=»', Plus: '«+»', Semicolon: '«;»', Comma: '«,»', In: '«Из»', Do: '«Цикл»',
  Then: '«Тогда»', EndDo: '«КонецЦикла»', EndIf: '«КонецЕсли»', EndFunction: '«КонецФункции»',
  RoundBracketClose: '«)»', RoundBracketOpen: '«(»', SquareBracketClose: '«]»',
};
const ruMsg = (m) => String(m)
  .replace(/Expecting symbol:\s*([A-Za-z]+)/i, (_, s) => `ожидается ${SYM[s] || `«${s}»`}`)
  .replace(/Identifier expecting/i, 'ожидается имя (идентификатор)')
  .replace(/Expression syntax error/i, 'ошибка в выражении')
  .replace(/Unexpected/i, 'неожиданный оператор');

function compileErrors(cat, detail) {
  const M = detail.M || {};
  const out = [];
  if (cat === 'B') {
    const msgs = M.compile_errors || [], lines = M.compile_error_lines || [];
    msgs.forEach((m, i) => out.push(lines[i] != null ? `строка ${lines[i]} · ${ruMsg(m)}` : ruMsg(m)));
  } else {
    for (const e of M.errors || []) {
      const mm = String(e).match(/Error in line\s+(\d+)(?:,\d+)?\s*\/\s*([^}]+)/);
      out.push(mm ? `строка ${mm[1]} · ${ruMsg(mm[2].trim())}`
        : ruMsg(String(e).replace(/^compile_error:\s*/, '').replace(/\{Модуль[^/]*\/\s*/, '').replace(/\}\s*$/, '').trim()));
    }
  }
  return out.filter(Boolean);
}

/* Номера строк ошибок в коде кандидата — чтобы подсветить их в панели кода.
   A: OneScript «Error in line N»; B: строки компилятора 1С + лог «…Модуль(N)». */
function errLines(cat, detail) {
  const M = detail.M || {}, set = new Set();
  (M.compile_error_lines || []).forEach((n) => Number.isFinite(n) && set.add(n));
  const scan = (s) => {
    const str = String(s);
    let m; const re1 = /Error in line\s+(\d+)/g, re2 = /Модуль\((\d+)/g;
    while ((m = re1.exec(str))) set.add(+m[1]);
    while ((m = re2.exec(str))) set.add(+m[1]);
  };
  (M.errors || []).forEach(scan);
  if (M.log) scan(M.log);
  return [...set].filter((n) => n > 0).sort((a, b) => a - b);
}

/* Человеческий перевод рантайм-ошибок 1С — чтобы было ясно, это код модели или тест.
   «Метод объекта не обнаружен (X)»: тест зовёт КодКандидата.X (X — обнаруженная точка входа),
   а 1С её не видит как метод модуля → функция НЕ экспортирована (забыт «Экспорт») или названа иначе.
   Это всегда ошибка кода модели, не теста. */
function humanizeBError(msg, mod) {
  const s = String(msg).trim();
  let m;
  if ((m = s.match(/Метод объекта не обнаружен\s*\(([^)]+)\)/i))) {
    // Тесты.Модуль → тест не смог позвать точку входа (не экспортирована); КодКандидата.Модуль →
    // кандидат сам вызвал несуществующий метод у объекта (напр. .Выбрать() у Неопределено) — баг кода.
    if (mod === 'Тесты')
      return `функция «${m[1]}» не вызывается извне — не экспортирована (нет «Экспорт») или названа иначе`;
    return `метод «${m[1]}» не найден — вызван у неподходящего значения (напр. у Неопределено или не того типа)`;
  }
  if ((m = s.match(/Поле объекта не обнаружено?\s*\(([^)]+)\)/i)))
    return `обращение к несуществующему полю/объекту «${m[1]}» — выдуманные метаданные`;
  if ((m = s.match(/Неверные параметры\s*"([^"]+)"/i)))
    return `неверные параметры виртуальной таблицы «${m[1]}» в запросе`;
  if ((m = s.match(/вызове конструктора\s*\(([^)]+)\):\s*Несоответствие типов\s*\(параметр номер\s*'?(\d+)'?\)/i)))
    return `неверный тип параметра ${m[2]} при создании «${m[1]}»`;
  if ((m = s.match(/вызове метода контекста\s*\(([^)]+)\):\s*Несоответствие типов\s*\(параметр номер\s*'?(\d+)'?\)/i)))
    return `неверный тип параметра ${m[2]} в вызове «${m[1]}»`;
  if ((m = s.match(/вызове конструктора\s*\(([^)]+)\)/i)))
    return `ошибка при создании объекта «${m[1]}» — неверные аргументы`;
  if ((m = s.match(/вызове метода контекста\s*\(([^)]+)\)/i)))
    return `ошибка при вызове «${m[1]}» — неверные аргументы`;
  if ((m = s.match(/Значение не является значением объектного типа\s*\(([^)]+)?\)?/i)))
    return `обращение как к объекту к неподходящему значению${m[1] ? ` («${m[1]}»)` : ''}`;
  // почистить остаточный шум: позиция {(N, N)}: и указатель запроса <<?>>…
  return s.replace(/\{\(\d+,\s*\d+\)\}:\s*/g, '').replace(/\s*<<\?>>[\s\S]*$/, '').trim();
}

/* Разобрать M.log категории B по тестам: «тест1 ИСКЛЮЧЕНИЕ: {…Тесты.Модуль(68)}: сообщение; тест2 …».
   Схлопываем одинаковые сообщения (три теста упали одинаково → одна строка), переводим на человеческий,
   отмечаем, упало ли ВНУТРИ кода модели (КодКандидата → есть строка кода) или на вызове из теста. */
function parseBLog(log) {
  if (!log) return { items: [], cause: null };
  const parts = String(log).split(/;+/).map((x) => x.trim()).filter(Boolean);
  const groups = new Map();
  let cause = null;
  for (const p of parts) {
    const m = p.match(/тест\s*(\d+)[^{]*\{[^}]*\.(КодКандидата|Тесты)\.Модул[ья]?\((\d+)\)\}\s*:?\s*(.+)$/i);
    let test = null, mod = null, line = null, raw = p;
    if (m) { test = +m[1]; mod = m[2]; line = +m[3]; raw = m[4].trim(); }
    const human = humanizeBError(raw, mod);
    if (/не вызывается извне/.test(human)) cause = 'entry';
    if (!groups.has(human)) groups.set(human, { human, tests: new Set(), inCand: mod === 'КодКандидата', line });
    if (test != null) groups.get(human).tests.add(test);
  }
  const items = [];
  for (const g of groups.values()) {
    const ts = [...g.tests].sort((a, b) => a - b);
    const where = !ts.length ? '' : ts.length >= 3 ? `тесты ${ts[0]}–${ts[ts.length - 1]}` : `тест ${ts.join(', ')}`;
    const src = g.inCand ? ` — в коде модели, строка ${g.line}` : '';
    items.push(`${where ? where + ': ' : ''}${g.human}${src}`);
  }
  return { items, cause };
}

/* Человеческий перевод рантайм-ошибок категории A (OneScript). Частый случай: модель применила
   платформенный тип (Запрос, РегистрыСведений…) в алгоритмической задаче — в OneScript его нет. */
function humanizeAMsg(msg) {
  const s = String(msg);
  let m;
  if ((m = s.match(/Type is not defined\s*\(([^)]+)\)/i)))
    return `применён тип «${m[1]}» — платформенный объект 1С, недоступный в алгоритмической задаче (чистый язык, без платформы)`;
  if ((m = s.match(/Method not found\s*\(([^)]+)\)/i)))
    return `метод «${m[1]}» не найден`;
  if ((m = s.match(/Variable not defined\s*\(([^)]+)\)/i)))
    return `переменная «${m[1]}» не определена`;
  if (/Invalid type of argument/i.test(s)) return 'неверный тип аргумента';
  if (/Division by zero|Деление на ноль/i.test(s)) return 'деление на ноль';
  if (/out of bound|за пределами|индекс/i.test(s)) return 'выход за границы массива или строки';
  return ruMsg(s);
}

/* Разобрать ошибки исполнения A (OneScript): «PRISM_ERR N {Модуль …cand.test.os / Error in line: L / MSG}».
   Достаём строку и текст, переводим, схлопываем дубли по тестам. Возвращаем причину для пояснения. */
function parseALog(errors) {
  const groups = new Map();
  let cause = null;
  for (const e of errors || []) {
    const s = (typeof e === 'string' ? e : JSON.stringify(e)).trim();
    if (!s || s === '{}' || s === '""') continue;
    const mm = s.match(/Error in line:?\s*(\d+)(?:,\d+)?\s*\/\s*([^}]+)/);
    let line = null, raw = s;
    if (mm) { line = Number(mm[1]); raw = mm[2].trim(); }
    const human = humanizeAMsg(raw);
    if (/платформенный объект/.test(human)) cause = 'platform-type';
    const key = `${human}|${line || ''}`;
    if (!groups.has(key)) groups.set(key, { human, line });
  }
  const items = [...groups.values()].map((g) => (g.line ? `строка ${g.line} · ${g.human}` : g.human));
  return { items, cause };
}

/* Диагностика задачи: что и где упало (исход + трейсбеки из auto_l1 detail).
   Исход — упрощённо для показа (агрегатная воронка считается харнессом). */
function diagnose(cat, detail) {
  const s = detail.S || {};
  const m = detail.M || {};
  const errors = [];
  const push = (arr) => {
    for (const e of arr || []) {
      const t = (typeof e === 'string' ? e : JSON.stringify(e)).trim();
      if (t && t !== '{}' && t !== '""') errors.push(t);
    }
  };
  const tests = { passed: m.passed ?? null, total: m.total ?? null };
  let outcome = 'unknown';
  let cause = null; // 'entry' — точка входа не найдена/не экспортирована (пояснение на витрине)
  if (cat === 'B') {
    if (m.status === 'candidate_error') { outcome = 'compile'; push(compileErrors('B', detail)); }
    else if (m.status === 'no_entry') {
      outcome = 'runtime'; cause = 'entry';
      errors.push('точка входа не найдена — модель не создала ожидаемую функцию или не экспортировала её');
    }
    else if ((m.total || 0) === 0 || (m.passed || 0) < (m.total || 0)) {
      const parsed = parseBLog(m.log);
      cause = parsed.cause;
      parsed.items.forEach((e) => errors.push(e));
      // платформенные маркеры / компиляцию добавляем ТОЛЬКО если разбор лога пуст — иначе дублируют
      if (!parsed.items.length) {
        (m.platform_errors || []).forEach((e) => errors.push(humanizeBError(e)));
        if (!(m.platform_errors || []).length) push(m.compile_errors);
      }
      outcome = (parsed.items.length || m.platform_errors?.length || m.platform_error_tests?.length) ? 'runtime' : 'wrong';
    } else outcome = 'solved';
  } else {
    if ((s.root_causes || 0) > 0) { outcome = 'compile'; push(compileErrors('A', detail)); }
    else if (!(m.executed && m.entry_point != null)) {
      outcome = 'runtime';
      const p = parseALog(m.errors); cause = p.cause; p.items.forEach((e) => errors.push(e));
    } else if ((m.total || 0) === 0 || (m.passed || 0) < (m.total || 0)) {
      const p = parseALog(m.errors); cause = p.cause;
      outcome = p.items.length ? 'runtime' : 'wrong';
      p.items.forEach((e) => errors.push(e));
    } else outcome = 'solved';
  }
  // какие тесты упали (кат. A): в ошибках «PRISM_ERR N» — N это 0-based индекс теста
  let failedIdx = null;
  if (cat === 'A') {
    const idx = new Set();
    for (const e of m.errors || []) { const mm = String(e).match(/PRISM_ERR\s+(\d+)/); if (mm) idx.add(Number(mm[1])); }
    failedIdx = [...idx].sort((a, b) => a - b);
  }
  return { outcome, tests, errors: [...new Set(errors)].slice(0, 6), cause, failedIdx };
}

/* Разбор оценки: по каждой оси — балл, человеческая причина, конкретная метрика, тег
   (full | warn | minus | na). Аргументирует, ЗА ЧТО балл, прямо из auto_l1 detail.
   Единица работы оси O категории B: perf-задачи мерятся исполнением (набором vs цикл),
   прочие — статикой (конкретный антипаттерн из detail.O.codes). */
function breakdown(cat, taskId, scores, detail) {
  const S = detail.S || {}, M = detail.M || {}, O = detail.O || {}, P = detail.P || {};
  const isPerf = cat === 'B' && PERF_B.has(taskId);
  const out = [];
  const add = (ax, score, head, metric, tag) =>
    out.push({ ax, score: score == null ? null : r1(score), head, metric, tag });

  // S — компилируется ли модуль
  const rc = S.root_causes ?? 0;
  if (rc === 0) add('S', scores.S, 'Компилируется без ошибок', 'синтаксис модуля чистый', 'full');
  else {
    // счёт берём из показываемых ошибок (не из кластеров BSL LS — иначе «2 ошибки, а видно одну»)
    const ce = compileErrors(cat, detail);
    const metric = (ce[0] || 'разбор модуля с ошибками') + (ce.length > 1 ? ` · и ещё ${ce.length - 1}` : '');
    add('S', scores.S, 'Не компилируется', metric, 'minus');
  }

  // M — верный ли ответ (исполнение скрытых тестов)
  const st = M.status, pd = M.passed, tt = M.total;
  if (cat === 'B' && st === 'candidate_error')
    add('M', scores.M, 'Код не исполнился', 'модуль не скомпилировался — тесты не запускались', 'minus');
  else if (tt > 0 && pd === tt)
    add('M', scores.M, 'Все скрытые тесты пройдены', `${pd}/${tt} проверок дали верный ответ`, 'full');
  else if (tt > 0 && pd > 0)
    add('M', scores.M, 'Часть тестов не пройдена', `${pd}/${tt} верны · балл = доля × 10`, 'warn');
  else {
    const plat = (M.platform_error_tests || 0) > 0;
    add('M', scores.M, plat ? 'Падает при обращении к базе' : 'Ответы неверны',
      tt > 0 ? `0/${tt} тестов пройдено` : 'тесты не пройдены', 'minus');
  }

  // O — оптимальность. Приоритет источника: замер ИСПОЛНЕНИЕМ (есть detail.O.growth —
  // A всегда по числу операций, B — по обращениям к СУБД после нагрузочного прогона) →
  // N/A с причиной (гейт: у нерабочего кода O не меряем) → статический разбор антипаттернов.
  const oG = O.growth, oPo = O.p_opt;
  if (oG != null) {
    const ok = oPo != null ? oG - oPo <= 0.2 : oG <= 0.2;
    if (cat === 'A') {
      add('O', scores.O, ok ? 'Оптимальный класс роста' : 'Класс роста хуже оптимума',
        `число операций растёт как ${growF(oG)}${oPo != null ? ` (оптимум ${growF(oPo)})` : ''}`,
        scores.O >= 8 ? 'full' : 'minus');
    } else { // B — обращения к СУБД на растущей базе
      const cs = O.counts || [], sz = O.sizes || [];
      const nums = (cs.length >= 2 && cs[0] != null && sz.length >= 2)
        ? `обращений к СУБД ${cs[0]}→${cs[cs.length - 1]} при росте базы ×${Math.round(sz[sz.length - 1] / sz[0])} · ` : '';
      add('O', scores.O, ok ? 'Оптимально: берёт данные набором' : 'Запрос в цикле',
        `${nums}растёт как ${growF(oG)}${oPo != null ? ` (оптимум ${growF(oPo)})` : ''}`, ok ? 'full' : 'minus');
    }
  } else if (scores.O == null) {
    add('O', null, cat === 'A' ? 'Не измерено' : 'Оптимальность не оценивается',
      cat === 'B' && st === 'candidate_error' ? 'код не скомпилировался — у нерабочего кода O не меряем'
        : (O.note ? String(O.note).slice(0, 90) : 'код не исполнился на нагрузочном прогоне'), 'na');
  } else { // статический разбор антипаттернов (B без нагрузочного замера)
    const wait = isPerf ? ' · нагрузочный замер не прогнан' : '';
    if (scores.O >= 10) add('O', scores.O, 'Явных антипаттернов нет', 'статический разбор кода чистый' + wait, 'full');
    else {
      const codes = (O.codes || []).map((c) => ANTI[c] || c);
      add('O', scores.O, 'Есть тяжёлый антипаттерн',
        (codes.length ? `статика: ${codes.join(', ')}` : 'статический разбор кода') + wait, 'minus');
    }
  }

  // P — платформа (только B)
  if (cat === 'B') {
    if (st === 'candidate_error')
      add('P', scores.P, 'Обращения к метаданным не подтверждены', 'код не запустился — проверить нечего', 'minus');
    else if ((scores.P ?? 0) >= 10)
      add('P', scores.P, 'Все обращения к метаданным отработали', '0 платформенных ошибок', 'full');
    else {
      const pe = M.platform_error_tests || 0, mk = (M.platform_errors || [])[0];
      add('P', scores.P, 'Падает на обращении к платформе',
        `${pe} ${plural(pe, 'тест', 'теста', 'тестов')} с ошибкой поля/объекта${mk ? ` · «${mk}»` : ''}`, 'minus');
    }
  }
  return out;
}

/* Данные нагрузочного замера O для графика: как растёт «стоимость» с размером входа/базы.
   A: число операций (codestat) на растущем входе; B: обращения к СУБД на растущей базе (после прогона).
   Есть только если замер реально исполнялся (detail.O.growth задан) — иначе вкладки нет. */
function perfData(cat, detail) {
  const O = detail.O || {};
  if (O.growth == null) return null;
  const sizes = O.sizes || [];
  const series = O.ops || O.counts || [];
  if (sizes.length < 2 || series.length !== sizes.length) return null;
  return {
    sizes,
    series,
    growth: r2(O.growth),                              // число — для расчёта «близко ли к оптимуму»
    pOpt: O.p_opt == null ? null : r2(O.p_opt),
    growthF: growF(O.growth),                       // формула для подписи (N¹, N¹·⁵)
    pOptF: growF(O.p_opt),
    unit: cat === 'A' ? 'операций' : 'обращений к СУБД',
    xlabel: cat === 'A' ? 'размер входа' : 'размер базы',
  };
}

function genTasks(name) {
  const out = [];
  for (const [cat, exp] of [['A', expA], ['B', expB]]) {
    const list = exp[name] || [];
    const scores = (cat === 'A' ? A : B).perTask[name] || {};
    for (const t of list) {
      const s = scores[t.taskId] || {};
      const sc = s.scores || {};
      out.push({
        taskId: t.taskId,
        taskName: t.taskName,
        category: cat,
        scores: { S: pick(sc.S), M: pick(sc.M), O: pick(sc.O), P: pick(sc.P), Q: r2(sc.Q) },
        diag: diagnose(cat, s.detail || {}),
        breakdown: breakdown(cat, t.taskId, sc, s.detail || {}),
        errorLines: errLines(cat, s.detail || {}),
        perf: perfData(cat, s.detail || {}),
        meta: t.meta,
        codeHtml: highlight(t.code),
        empty: !t.code,
      });
    }
  }
  return out.sort((x, y) => (x.category === y.category ? taskNum(x.taskId) - taskNum(y.taskId) : x.category < y.category ? -1 : 1));
}

let genCount = 0;
const writtenGen = new Set();
for (const m of models) {
  const tasks = genTasks(m.name);
  if (!tasks.length) continue;
  fs.writeFileSync(path.join(GEN_DIR, `${m.id}.json`), JSON.stringify({ id: m.id, name: m.name, tasks }));
  writtenGen.add(`${m.id}.json`);
  genCount += tasks.length;
}
// подчистить файлы моделей, которых больше нет в прогоне
for (const f of fs.readdirSync(GEN_DIR)) if (f.endsWith('.json') && !writtenGen.has(f)) fs.rmSync(path.join(GEN_DIR, f));

/* ---- 5b. Условие и тесты задач (одинаковы у всех моделей → отдельный tasks.json) ---- */
function loadTaskInfo() {
  const info = {};
  let cases = 0;
  for (const cat of ['a', 'b']) {
    const base = path.join(REPO, 'tasks', `category_${cat}`);
    if (!fs.existsSync(base)) continue;
    for (const dir of fs.readdirSync(base)) {
      const tp = path.join(base, dir, 'task.yaml');
      if (!fs.existsSync(tp)) continue;
      const t = readYAML(tp);
      // База 1С — распарсенная спека (рендерим карточками объектов, не YAML)
      const cfg = path.join(base, dir, 'config_spec.yaml');
      const config = fs.existsSync(cfg) ? readYAML(cfg) : null;
      // Тесты — A: структурированные кейсы (вход→ожидание); B: BSL-проверки (подсветка)
      const bsl = path.join(base, dir, 'tests.bsl');
      const yml = path.join(base, dir, 'tests.yaml');
      let testsHtml = '';
      let tests = null;
      if (fs.existsSync(bsl)) {
        const txt = fs.readFileSync(bsl, 'utf8');
        testsHtml = highlightAs(txt, 'bsl');
        cases += (txt.match(/^\s*(?:Процедура|Функция)\b/gim) || []).length;
      } else if (fs.existsSync(yml)) {
        tests = readYAML(yml).tests || [];
        cases += tests.length;
      }
      info[t.id] = {
        name: t.name || t.id,
        category: cat.toUpperCase(),
        prompt: (t.prompt || '').trim(),
        signature: t.signature || '',
        difficulty: t.difficulty || '',
        entryPoint: t.entry_point || '',
        tags: t.tags || {},
        config,
        tests,
        testsHtml,
      };
    }
  }
  return { info, cases };
}
const taskInfo = loadTaskInfo();
fs.writeFileSync(path.join(WEB, 'public', 'data', 'tasks.json'), JSON.stringify(taskInfo.info));

/* ---- 5c. Мета страницы задач: параметры генерации + системные промпты ---- */
const params = readYAML(path.join(REPO, 'generation', 'params.yaml')) || {};
const promptsCfg = readYAML(path.join(REPO, 'generation', 'prompts.yaml')) || {};
const mp = params.defaults?.model_params || params.model_params || {};
const temps = [...new Set(Object.values(mp).map((m) => m.temperature).filter((v) => v != null))];
const runsSet = [...new Set(Object.values(mp).map((m) => m.runs).filter((v) => v != null))];
const tasksMeta = {
  params: {
    max_tokens: params.defaults?.max_tokens ?? null,
    concurrency: params.defaults?.concurrency ?? null,
    temperature: temps.length === 1 ? temps[0] : temps,        // у всех 0.1 → одно число
    runs: runsSet.length === 1 ? runsSet[0] : runsSet,
  },
  prompts: { A: (promptsCfg.system?.A || '').trim(), B: (promptsCfg.system?.B || '').trim() },
  order: Object.entries(taskInfo.info)
    .map(([id, t]) => ({ id, name: t.name, category: t.category, difficulty: t.difficulty }))
    .sort((a, b) => (a.category === b.category ? taskNum(a.id) - taskNum(b.id) : a.category < b.category ? -1 : 1)),
};
fs.writeFileSync(path.join(WEB, 'public', 'data', 'tasks_meta.json'), JSON.stringify(tasksMeta));

// тест-кейсы и генерации — берём из бейджей README (их считает `prism docs`), чтобы 1:1 с публикацией
const readme = fs.readFileSync(path.join(REPO, 'README.md'), 'utf8');
const badgeNum = (re) => { const m = readme.match(re); return m ? Number(m[1]) : null; };
const nodeGens = Object.values(expA).reduce((s, l) => s + l.length, 0) + Object.values(expB).reduce((s, l) => s + l.length, 0);
const gens = badgeNum(/badge\/генераций[^-]*-(\d+)/) ?? nodeGens;
const cases = badgeNum(/badge\/тест--кейсов-(\d+)/) ?? taskInfo.cases;

/* ---- 6. Мета для шапки/чипов ---- */
const pyproject = fs.readFileSync(path.join(REPO, 'pyproject.toml'), 'utf8');
const version = (pyproject.match(/version\s*=\s*"([^"]+)"/) || [])[1] || '';
const dateOf = (exp) => { const m = (exp || '').match(/_(\d{4})(\d{2})(\d{2})_/); return m ? `${m[1]}-${m[2]}-${m[3]}` : ''; };
// дата прогона = дата ПОСЛЕДНЕЙ генерации (поле timestamp в рулоне, оно обновляется при
// каждом generate/--resume), а не дата из имени файла (первый прогон). Фолбэк — имя файла.
const expTimestamp = (cat) => { try { const f = expFile(cat); return f ? (readJSON(path.join(RESULTS, f)).timestamp || '') : ''; } catch { return ''; } };
const lastRunIso = [expTimestamp('A'), expTimestamp('B')].filter(Boolean).sort().pop() || '';
const lastRun = /^\d{4}-\d{2}-\d{2}/.test(lastRunIso) ? lastRunIso.slice(0, 10) : dateOf(B.exp);
const tasksA = Math.max(0, ...Object.values(A.summary).map((m) => m.taskCount));
const tasksB = Math.max(0, ...Object.values(B.summary).map((m) => m.taskCount));

/* ---- 6b. Репозиторий и звёзды (для ссылки/бейджа в шапке) ----
   Звёзды тянем с GitHub API на билде; офлайн/недоступно → null (бейдж без числа). */
const GH_REPO = 'genlab-1c/prism';
let repoStars = null;
try {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 4000); // не вешать сборку, если сети нет
  const r = await fetch(`https://api.github.com/repos/${GH_REPO}`, { headers: { 'User-Agent': 'prism-web' }, signal: ctrl.signal });
  clearTimeout(t);
  if (r.ok) repoStars = (await r.json()).stargazers_count ?? null;
} catch { /* офлайн или лимит API — бейдж покажем без числа */ }

const OUT = path.join(WEB, 'src', 'data', 'leaderboard.json');
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({
  meta: { version, models: models.length, tasksA, tasksB, gens, cases, lastRun, profileCols, tagLabels, repo: { url: `https://github.com/${GH_REPO}`, stars: repoStars } },
  models,
}, null, 2) + '\n');

console.log(`✓ leaderboard.json — ${models.length} моделей · A ${tasksA} / B ${tasksB} задач · v${version}`);
console.log(`✓ public/data/gen — ${models.length} файлов, ${genCount} генераций с подсветкой BSL`);
