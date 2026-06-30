/* PRISM web — авто-нарратив по модели из данных лидерборда.
   Никакого ручного текста: ранги, соседи, множители цены и слабые места
   вычисляются из массива моделей. Один источник правды — leaderboard.json. */

const AXIS_LABEL = { S: 'синтаксис', M: 'логика', O: 'оптимизация', P: 'платформа 1С' };

const rankBy = (models, key) => {
  const ranked = models.filter((m) => m[key] != null).sort((a, b) => b[key] - a[key]);
  const rank = {};
  ranked.forEach((m, i) => { rank[m.id] = i + 1; });
  return { rank, total: ranked.length, ordered: ranked };
};

// самая слабая ось категории (с её баллом) — «не для алгоритмики», «проседает логика»
function weakestAxis(scores, order) {
  if (!scores) return null;
  let lo = null;
  for (const ax of order) {
    const v = scores[ax];
    if (v == null) continue;
    if (!lo || v < lo.value) lo = { axis: ax, value: v, label: AXIS_LABEL[ax] };
  }
  return lo;
}

// худший навык/конструкция по профилю (M для A, P для B) — конкретика «слаба на строках»
function weakestTag(catData, labels) {
  const prof = catData?.profile;
  if (!prof) return null;
  let lo = null;
  for (const [tag, cell] of Object.entries(prof)) {
    const v = cell?.value;
    if (v == null) continue;
    if (!lo || v < lo.value) lo = { tag, value: v, label: (labels && labels[tag]) || tag };
  }
  return lo;
}

// курс для отображения: цены в данных в USD, на сайте показываем рубли (как в pricing.yaml ~85)
export const RUB_PER_USD = 85;
const fmtMult = (x) => (x >= 10 ? `${Math.round(x)}×` : `${x.toFixed(1).replace(/\.0$/, '')}×`);
export const fmtRub = (usd) => {
  if (usd == null) return '—';
  const r = usd * RUB_PER_USD;
  return r < 1 ? `${r.toFixed(1)} ₽` : r < 100 ? `${Math.round(r)} ₽` : `${Math.round(r)} ₽`;
};
const fmtCost = fmtRub;

/* Главная: структурные факты о модели относительно остальных. */
export function buildInsights(model, models, tagLabels = {}) {
  const overall = rankBy(models, 'qOverall');
  const a = rankBy(models, 'qA');
  const b = rankBy(models, 'qB');

  const rO = overall.rank[model.id];
  const total = overall.total;

  // кому уступает (выше в общем зачёте) / кого обходит (ниже) — ближайшие по рейтингу
  const idx = overall.ordered.findIndex((m) => m.id === model.id);
  const above = overall.ordered.slice(0, idx);
  const below = overall.ordered.slice(idx + 1);
  const losesTo = above.slice(-3).reverse().map((m) => m.name); // ближайшие сверху
  const beats = below.slice(0, 3).map((m) => m.name);            // ближайшие снизу (самые статусные)

  // сильная категория — где выше Q (для 1С обычно профильная B); показываем всегда
  const strongCat = (model.qB != null && model.qA != null)
    ? (model.qB >= model.qA ? 'B' : 'A')
    : (model.qB != null ? 'B' : model.qA != null ? 'A' : null);
  const strongQ = strongCat === 'B' ? model.qB : model.qA;
  const strongS = strongCat === 'B' ? model.B?.S : model.A?.S;

  // слабость — самая низкая ОСЬ по обеим категориям; озвучиваем, только если реально низкая
  const WEAK_THRESHOLD = 7;
  const cands = [
    ...(model.A ? [{ ...weakestAxis(model.A, ['S', 'M', 'O']), cat: 'A' }] : []),
    ...(model.B ? [{ ...weakestAxis(model.B, ['S', 'M', 'O', 'P']), cat: 'B' }] : []),
  ].filter((x) => x && x.value != null);
  cands.sort((x, y) => x.value - y.value);
  const weakSpot = cands[0] && cands[0].value < WEAK_THRESHOLD ? cands[0] : null;
  const weakCat = weakSpot?.cat || null;
  const weakTag = weakCat === 'A'
    ? weakestTag(model.A, tagLabels)
    : weakCat === 'B' ? weakestTag(model.B, tagLabels) : null;

  // экономика: дешевле ли всех, кто выше; множители против названных конкурентов
  const myCost = model.econ?.runCost ?? null;
  const named = [...losesTo, ...beats];
  const cheaperThan = [];
  if (myCost != null && myCost > 0) {
    for (const nm of named) {
      const other = models.find((m) => m.name === nm);
      const oc = other?.econ?.runCost;
      if (oc != null && oc / myCost >= 1.3) cheaperThan.push({ name: nm, mult: fmtMult(oc / myCost) });
    }
  }
  const aboveCosts = above.map((m) => m.econ?.runCost).filter((c) => c != null);
  const cheaperThanAllAbove = myCost != null && aboveCosts.length > 0 && aboveCosts.every((c) => c > myCost);
  // кто дешевле, но слабее (как DeepSeek) — честная оговорка
  const cheaperButWeaker = below
    .filter((m) => m.econ?.runCost != null && myCost != null && m.econ.runCost < myCost)
    .map((m) => m.name);

  // скорость и токены относительно группы
  const times = models.map((m) => m.econ?.avgTime).filter((t) => t != null);
  const slowest = model.econ?.avgTime != null && times.length > 0 && model.econ.avgTime >= Math.max(...times);
  const outs = models.map((m) => m.econ?.tokensOut).filter((t) => t != null).sort((x, y) => x - y);
  const median = outs.length ? outs[Math.floor(outs.length / 2)] : null;
  const economical = model.econ?.tokensOut != null && median != null && model.econ.tokensOut <= median;

  return {
    name: model.name,
    family: model.family,
    rankOverall: rO, total,
    qOverall: model.qOverall,
    rankA: a.rank[model.id], totalA: a.total, qA: model.qA,
    rankB: b.rank[model.id], totalB: b.total, qB: model.qB,
    losesTo, beats,
    strongCat, strongQ, strongS, weakCat, weakSpot, weakTag,
    runCost: myCost, runCostFmt: fmtCost(myCost),
    cheaperThan, cheaperThanAllAbove, cheaperButWeaker,
    tokensOut: model.econ?.tokensOut ?? null, economical,
    avgTime: model.econ?.avgTime ?? null, slowest,
    bScores: model.B, aScores: model.A,
  };
}

const catName = (c) => (c === 'B' ? 'платформа 1С (запросы, регистры, метаданные)' : 'алгоритмика');
const list = (arr) => (arr.length === 1 ? arr[0] : `${arr.slice(0, -1).join(', ')} и ${arr[arr.length - 1]}`);

/* Готовый текст поста — тот самый формат «прогнал X → топ-N». Plain-язык.
   opts: { version, url } — провенанс (версия бенчмарка + канонический адрес + авторство). */
export function narrativeText(ins, opts = {}) {
  const L = [];
  L.push(`прогнал ${ins.name}`);
  const topN = ins.rankOverall <= 3 ? `вошёл в топ-${ins.rankOverall === 1 ? '1' : ins.rankOverall} общего зачёта` : `${ins.rankOverall}-е место из ${ins.total} в общем зачёте`;
  let line = topN + '.';
  if (ins.beats.length) line += ` обходит ${list(ins.beats)}`;
  if (ins.losesTo.length) line += `${ins.beats.length ? ', ' : ' '}уступает ${list(ins.losesTo)}`;
  L.push(line + '.');

  if (ins.strongCat) {
    const lead = ins.strongQ >= 7 ? 'особенно силён на категории' : 'из двух категорий лучше даётся';
    let s = `${lead} ${ins.strongCat} — ${catName(ins.strongCat)}, Q̄ ${ins.strongQ?.toFixed(2)}`;
    if (ins.strongS === 10) s += ', при идеальном синтаксисе (S 10)';
    L.push(s + '.');
  }
  if (ins.weakSpot) {
    let w = `слабее в категории ${ins.weakCat} — проседает ${ins.weakSpot.label} (${ins.weakSpot.axis} ${ins.weakSpot.value})`;
    if (ins.weakTag) w += `, особенно «${ins.weakTag.label}»`;
    L.push(w + '.');
  }

  if (ins.runCost != null) {
    let c = `${ins.runCostFmt} за полный прогон`;
    if (ins.cheaperThan.length) c += ` — ${list(ins.cheaperThan.map((x) => `в ${x.mult} дешевле ${x.name}`))}`;
    L.push(c + '.');
    if (ins.cheaperThanAllAbove) L.push('дешевле всех, кто выше по рейтингу — а всё, что дешевле, уступает в качестве.');
  }

  if (ins.economical) L.push(`экономный на токенах — ${(ins.tokensOut / 1000).toFixed(0)}k на выходе, отвечает по делу.`);
  if (ins.slowest && ins.avgTime != null) L.push(`минус — скорость: ${ins.avgTime}с на задачу, самый медленный в группе.`);

  // провенанс: версия + канонический адрес + авторство — чтобы пост был атрибутирован
  L.push('');
  L.push('— PRISM · исполняемый бенчмарк кода 1С (методика SMOP)');
  L.push(`оценка L1 (машина)${opts.version ? ` · бенчмарк v${opts.version}` : ''}`);
  if (opts.url) L.push(opts.url);
  L.push('источник и методика: github.com/genlab-1c/prism · © genlab-1c');
  return L.join('\n');
}

/* Однострочная сводка для OG-описания и мета-тегов. */
export function shortSummary(ins) {
  const parts = [];
  parts.push(ins.rankOverall <= 3 ? `ТОП-${ins.rankOverall} общего зачёта` : `${ins.rankOverall}-е из ${ins.total} в общем зачёте`);
  if (ins.strongCat) parts.push(`силён на категории ${ins.strongCat} (Q̄ ${ins.strongQ?.toFixed(2)})`);
  if (ins.runCost != null) parts.push(`${ins.runCostFmt} за прогон`);
  return parts.join(' · ');
}
