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
};

const findFile = (dir, prefix, suffix) =>
  fs.readdirSync(dir).find((f) => f.startsWith(prefix) && f.endsWith(suffix));
const autoFile = (cat) => findFile(AUTO, `experiment_${cat}_`, '_auto_l1.json');
const expFile = (cat) => findFile(RESULTS, `experiment_${cat}_`, '.json');

const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const r1 = (v) => (v == null ? null : Math.round(v * 10) / 10);
const r2 = (v) => (v == null ? null : Math.round(v * 100) / 100);
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const taskNum = (id) => parseInt(String(id).replace(/\D/g, ''), 10) || 0;

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
  const summary = {};
  for (const [name, a] of Object.entries(agg)) {
    summary[name] = { id: a.id, taskCount: a.tasks.size, S: mean(a.S), M: mean(a.M), O: mean(a.O), P: mean(a.P), Q: mean(a.Q) };
  }
  return { exp: auto.experiment_id, summary, perTask };
}

const A = loadAuto('A');
const B = loadAuto('B');

/* ---- 2. Код: код, который писали модели (из рулона эксперимента) ---- */
function extractCode(resp) {
  if (!resp) return '';
  const m = resp.match(/```[a-zA-Z0-9]*\n([\s\S]*?)```/); // вынимаем из markdown-фенса
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
const costOf = (id) => {
  const p = pricing[id];
  if (!p) return '—';
  return `$${(((p.input + p.output) / 2) / 1000).toFixed(3)} / 1k`;
};

const names = new Set([...Object.keys(A.summary), ...Object.keys(B.summary)]);
const models = [...names].map((name) => {
  const a = A.summary[name];
  const b = B.summary[name];
  const meta = byName[name] || {};
  return {
    id: slug(name),
    name,
    family: VENDOR[meta.vendor] || meta.vendor || '',
    cost: costOf(meta.id),
    A: a ? { S: r1(a.S), M: r1(a.M), O: r1(a.O) } : null,
    B: b ? { S: r1(b.S), M: r1(b.M), O: r1(b.O), P: r1(b.P) } : null,
    qA: a ? r2(a.Q) : null,
    qB: b ? r2(b.Q) : null,
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
const GEN_DIR = path.join(WEB, 'public', 'data', 'gen');
fs.rmSync(GEN_DIR, { recursive: true, force: true });
fs.mkdirSync(GEN_DIR, { recursive: true });

const pick = (s) => (s == null ? null : r1(s)); // оси задачи — к одному знаку

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
  if (cat === 'B') {
    if (m.status === 'candidate_error') { outcome = 'compile'; push(m.compile_errors); push(s.errors); }
    else if (m.status === 'no_entry') { outcome = 'runtime'; }
    else if ((m.total || 0) === 0 || (m.passed || 0) < (m.total || 0)) {
      outcome = (m.platform_errors?.length || m.platform_error_tests?.length) ? 'runtime' : 'wrong';
      push(m.platform_errors); push(m.compile_errors); if (m.log) push([m.log]);
    } else outcome = 'solved';
  } else {
    if ((s.root_causes || 0) > 0) { outcome = 'compile'; push(s.errors); push(s.error_codes); }
    else if (!(m.executed && m.entry_point != null)) { outcome = 'runtime'; push(m.errors); }
    else if ((m.total || 0) === 0 || (m.passed || 0) < (m.total || 0)) {
      outcome = m.errors?.length ? 'runtime' : 'wrong';
      push(m.errors);
    } else outcome = 'solved';
  }
  return { outcome, tests, errors: [...new Set(errors)].slice(0, 6) };
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
        meta: t.meta,
        codeHtml: highlight(t.code),
        empty: !t.code,
      });
    }
  }
  return out.sort((x, y) => (x.category === y.category ? taskNum(x.taskId) - taskNum(y.taskId) : x.category < y.category ? -1 : 1));
}

let genCount = 0;
for (const m of models) {
  const tasks = genTasks(m.name);
  if (!tasks.length) continue;
  fs.writeFileSync(path.join(GEN_DIR, `${m.id}.json`), JSON.stringify({ id: m.id, name: m.name, tasks }));
  genCount += tasks.length;
}

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
        prompt: (t.prompt || '').trim(),
        signature: t.signature || '',
        difficulty: t.difficulty || '',
        entryPoint: t.entry_point || '',
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
const tasksA = Math.max(0, ...Object.values(A.summary).map((m) => m.taskCount));
const tasksB = Math.max(0, ...Object.values(B.summary).map((m) => m.taskCount));

const OUT = path.join(WEB, 'src', 'data', 'leaderboard.json');
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({
  meta: { version, models: models.length, tasksA, tasksB, gens, cases, lastRun: dateOf(B.exp), profileCols, tagLabels },
  models,
}, null, 2) + '\n');

console.log(`✓ leaderboard.json — ${models.length} моделей · A ${tasksA} / B ${tasksB} задач · v${version}`);
console.log(`✓ public/data/gen — ${models.length} файлов, ${genCount} генераций с подсветкой BSL`);
