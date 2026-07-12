/* ============================================================
   PRISM web — генерация OG-картинок (превью при шеринге) по моделям.
   satori (вёрстка → SVG) + sharp (SVG → PNG). Запускается ПОСЛЕ build-data.mjs
   (нужен src/data/leaderboard.json) и только на сборке (см. npm run build) —
   в dev не нужно. Шрифт с кириллицей бандлится в репо → сборка герметична.
   На выходе: public/og/<model>.png (1200×630), на них ссылается /m/[id].astro.
   ============================================================ */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import satori from 'satori';
import sharp from 'sharp';
import { buildInsights } from '../src/lib/insights.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.join(HERE, '..');
const data = JSON.parse(fs.readFileSync(path.join(WEB, 'src', 'data', 'leaderboard.json'), 'utf8'));
const FONTS = path.join(HERE, 'assets', 'fonts');
const fontRegular = fs.readFileSync(path.join(FONTS, 'LiberationSans-Regular.ttf'));
const fontBold = fs.readFileSync(path.join(FONTS, 'LiberationSans-Bold.ttf'));

// палитра темы (значения из src/styles/tokens/colors.css — vars satori не понимает)
const C = {
  bg: '#0c1626', card: '#131d2e', line: '#1f2c40',
  ink1: '#eef2f8', ink3: '#8e9cb3', ink4: '#61708a',
  brand: '#22d3ee', brandInk: '#04222a', o: '#34d399', p: '#fbbf24',
};
const PRISM = ['#7c7ef8', '#22d3ee', '#34d399', '#fbbf24']; // s · m · o · p

// мини-хелпер вместо JSX: h(type, style|props, ...children)
const h = (type, props, ...children) => ({ type, props: { ...props, children: children.length <= 1 ? children[0] : children } });
const text = (s, style) => h('div', { style: { display: 'flex', ...style } }, String(s));

function card(model) {
  const ins = buildInsights(model, data.models, data.meta?.tagLabels || {});
  const podium = ins.rankOverall <= 3;
  const rankText = podium ? `ТОП-${ins.rankOverall}` : `#${ins.rankOverall}`;

  const lines = [];
  if (ins.beats.length) lines.push(['обходит', C.ink3, ins.beats.slice(0, 2).join(', '), C.ink1]);
  if (ins.strongCat) lines.push([`силён · ${ins.strongCat} — ${ins.strongCat === 'B' ? 'платформа 1С' : 'алгоритмика'} ·`, C.ink3, `Q ${ins.strongQ?.toFixed(2)}${ins.strongS === 10 ? ' · S 10' : ''}`, C.ink1]);
  const costTail = ins.cheaperThan.length ? `· ${ins.cheaperThan.slice(0, 2).map((x) => `${x.mult} дешевле ${x.name}`).join(' · ')}` : '';
  // в bundled-шрифте OG нет глифа ₽ → пишем «руб» (на сайте/в посте символ ₽ остаётся)
  if (ins.runCost != null) lines.push([`${ins.runCostFmt.replace('₽', 'руб')} за прогон`, C.o, costTail, C.ink3]);

  return h('div', {
    style: {
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      width: '1200px', height: '630px', padding: '60px 64px', background: C.bg,
      fontFamily: 'Liberation Sans', color: C.ink1,
    },
  },
    // верхняя планка призмы
    h('div', { style: { display: 'flex', position: 'absolute', top: '0px', left: '0px', width: '1200px', height: '8px' } },
      ...PRISM.map((c) => h('div', { style: { display: 'flex', flex: '1', background: c } }))),
    // шапка
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
      text('РАЗБОР ПРОГОНА · L1', { fontSize: '24px', letterSpacing: '4px', color: C.ink4 }),
      text('prism', { fontSize: '34px', fontWeight: 700, color: C.brand, letterSpacing: '1px' }),
    ),
    // центр
    h('div', { style: { display: 'flex', flexDirection: 'column' } },
      h('div', { style: { display: 'flex', alignItems: 'center', marginBottom: '14px' } },
        text(rankText, { fontSize: '34px', fontWeight: 700, color: podium ? C.brandInk : C.ink1, background: podium ? C.brand : C.card, padding: '6px 22px', borderRadius: '999px', marginRight: '20px' }),
        text(`из ${ins.total} в общем зачёте`, { fontSize: '26px', color: C.ink4 }),
      ),
      text(model.name, { fontSize: '78px', fontWeight: 700, color: C.ink1, lineHeight: '1.05' }),
      text(model.family || '', { fontSize: '30px', color: C.ink3, marginTop: '6px' }),
      h('div', { style: { display: 'flex', flexDirection: 'column', marginTop: '26px' } },
        ...lines.map(([a, ca, b, cb]) => h('div', { style: { display: 'flex', fontSize: '31px', marginBottom: '12px' } },
          text(a, { color: ca, marginRight: b ? '10px' : '0' }), b ? text(b, { color: cb, fontWeight: 700 }) : null,
        )),
      ),
    ),
    // подвал — с версией и авторством (провенанс картинки)
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: `1px solid ${C.line}`, paddingTop: '22px' } },
      text(`исполняемый бенчмарк кода 1С · SMOP · L1${data.meta?.version ? ` · v${data.meta.version}` : ''}`, { fontSize: '23px', color: C.ink4 }),
      text('github.com/genlab-1c', { fontSize: '23px', color: C.ink3 }),
    ),
  );
}

// обложка главной страницы (og:image по умолчанию, не привязана к модели):
// бренд + ключевые числа прогона. Генерируется здесь, а не кладётся файлом, —
// иначе финальная чистка каталога ниже снесла бы её как «лишнюю».
function homeCard() {
  const m = data.meta || {};
  const stats = [
    [String((m.tasksA || 0) + (m.tasksB || 0)), 'задач'],
    [String(m.cases || 0), 'тест-кейсов'],
    [String(m.gens || 0), 'генераций'],
    [String(m.models || 0), 'моделей'],
  ];
  return h('div', {
    style: {
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      width: '1200px', height: '630px', padding: '60px 64px', background: C.bg,
      fontFamily: 'Liberation Sans', color: C.ink1,
    },
  },
    h('div', { style: { display: 'flex', position: 'absolute', top: '0px', left: '0px', width: '1200px', height: '8px' } },
      ...PRISM.map((c) => h('div', { style: { display: 'flex', flex: '1', background: c } }))),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
      text('ИСПОЛНЯЕМЫЙ БЕНЧМАРК КОДА 1С · SMOP', { fontSize: '24px', letterSpacing: '4px', color: C.ink4 }),
      text('prism', { fontSize: '34px', fontWeight: 700, color: C.brand, letterSpacing: '1px' }),
    ),
    h('div', { style: { display: 'flex', flexDirection: 'column' } },
      text('PRISM', { fontSize: '104px', fontWeight: 700, color: C.ink1, lineHeight: '1.0' }),
      text('какая нейросеть лучше пишет код на 1С', { fontSize: '38px', color: C.ink3, marginTop: '10px' }),
      h('div', { style: { display: 'flex', marginTop: '28px' } },
        ...['S', 'M', 'O', 'P'].map((a, i) => text(a, { fontSize: '30px', fontWeight: 700, color: PRISM[i], background: C.card, padding: '6px 20px', borderRadius: '12px', marginRight: '12px' })),
      ),
    ),
    h('div', { style: { display: 'flex', flexDirection: 'column' } },
      h('div', { style: { display: 'flex', marginBottom: '22px' } },
        ...stats.map(([v, l]) => h('div', { style: { display: 'flex', alignItems: 'baseline', marginRight: '30px' } },
          text(v, { fontSize: '42px', fontWeight: 700, color: C.brand, marginRight: '10px' }),
          text(l, { fontSize: '26px', color: C.ink3 }),
        )),
      ),
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: `1px solid ${C.line}`, paddingTop: '22px' } },
        text(`оценка исполнением по осям SMOP${data.meta?.version ? ` · v${data.meta.version}` : ''}`, { fontSize: '23px', color: C.ink4 }),
        text('github.com/genlab-1c/prism', { fontSize: '23px', color: C.ink3 }),
      ),
    ),
  );
}

const FONT_SET = [
  { name: 'Liberation Sans', data: fontRegular, weight: 400, style: 'normal' },
  { name: 'Liberation Sans', data: fontBold, weight: 700, style: 'normal' },
];
const render = async (node) => sharp(Buffer.from(await satori(node, { width: 1200, height: 630, fonts: FONT_SET }))).png().toBuffer();

const OUT = path.join(WEB, 'public', 'og');
fs.mkdirSync(OUT, { recursive: true }); // не сносим каталог целиком — обновляем на месте

let n = 0;
const written = new Set();

fs.writeFileSync(path.join(OUT, 'home.png'), await render(homeCard())); // обложка главной
written.add('home.png');

for (const model of data.models) {
  fs.writeFileSync(path.join(OUT, `${model.id}.png`), await render(card(model)));
  written.add(`${model.id}.png`);
  n += 1;
}
for (const f of fs.readdirSync(OUT)) if (f.endsWith('.png') && !written.has(f)) fs.rmSync(path.join(OUT, f));
console.log(`✓ public/og — обложка home.png + ${n} карточек моделей (1200×630, satori+sharp)`);
