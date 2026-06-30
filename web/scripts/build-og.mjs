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

const OUT = path.join(WEB, 'public', 'og');
fs.mkdirSync(OUT, { recursive: true }); // не сносим каталог целиком — обновляем на месте

let n = 0;
const written = new Set();
for (const model of data.models) {
  const svg = await satori(card(model), {
    width: 1200, height: 630,
    fonts: [
      { name: 'Liberation Sans', data: fontRegular, weight: 400, style: 'normal' },
      { name: 'Liberation Sans', data: fontBold, weight: 700, style: 'normal' },
    ],
  });
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  fs.writeFileSync(path.join(OUT, `${model.id}.png`), png);
  written.add(`${model.id}.png`);
  n += 1;
}
for (const f of fs.readdirSync(OUT)) if (f.endsWith('.png') && !written.has(f)) fs.rmSync(path.join(OUT, f));
console.log(`✓ public/og — ${n} OG-картинок (1200×630, satori+sharp)`);
