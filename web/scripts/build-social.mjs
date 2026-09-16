/* ============================================================
   PRISM web — превью репозитория для GitHub (Settings → Social preview).
   Та же техника, палитра и шрифт, что у OG-картинок моделей (build-og.mjs):
   satori → SVG → sharp → PNG. Минималистичная раскладка: знак и название по центру,
   одна строка под ними. Меняющихся чисел нет — картинка загружается вручную и не обновляется.
   GitHub не берёт её из репозитория сам, поэтому скрипт запускается руками и в сборку не входит:
     node scripts/build-social.mjs            → docs/assets/social-preview.png
     node scripts/build-social.mjs --variants → work/social/*.png (сравнить варианты)
   Размер 1280×640 — рекомендуемый GitHub.
   ============================================================ */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import satori from 'satori';
import sharp from 'sharp';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.join(HERE, '..');
const REPO = path.join(WEB, '..');
const FONTS = path.join(HERE, 'assets', 'fonts');
const FONT_SET = [
  { name: 'Liberation Sans', data: fs.readFileSync(path.join(FONTS, 'LiberationSans-Regular.ttf')), weight: 400, style: 'normal' },
  { name: 'Liberation Sans', data: fs.readFileSync(path.join(FONTS, 'LiberationSans-Bold.ttf')), weight: 700, style: 'normal' },
];

// палитра темы (значения из src/styles/tokens/colors.css — vars satori не понимает)
const C = { bg: '#0c1626', ink1: '#eef2f8', ink3: '#8e9cb3', ink4: '#61708a', brand: '#22d3ee' };
const SPECTRUM = ['#7c7ef8', '#22d3ee', '#34d399', '#fbbf24']; // S · M · O · P
const W = 1280, H = 640;

const h = (type, props, ...children) => ({ type, props: { ...props, children: children.length <= 1 ? children[0] : children } });
const text = (s, style) => h('div', { style: { display: 'flex', ...style } }, String(s));

// знак — векторная призма бренда (scripts/assets/prism-mark.svg). favicon.svg не годится:
// он нарисован под 32 px и на крупном размере даёт неровную точку схода лучей
const MARK_H = 150, MARK_W = Math.round(MARK_H * 214 / 118);
const icon = await sharp(fs.readFileSync(path.join(HERE, 'assets', 'prism-mark.svg')), { density: 600 }).resize(MARK_W, MARK_H).png().toBuffer();
const iconSrc = `data:image/png;base64,${icon.toString('base64')}`;

// accent: none — только знак и строка; line — короткая спектральная черта между ними
function layout({ accent }) {
  return h('div', {
    style: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      width: `${W}px`, height: `${H}px`, background: C.bg, fontFamily: 'Liberation Sans', color: C.ink1 },
  },
    h('div', { style: { display: 'flex', alignItems: 'center', gap: '36px' } },
      h('img', { src: iconSrc, width: MARK_W, height: MARK_H }),
      text('PRISM', { fontSize: '132px', fontWeight: 700, letterSpacing: '6px', lineHeight: 1 }),
    ),
    accent === 'line'
      ? h('div', { style: { display: 'flex', width: '220px', height: '6px', marginTop: '44px', borderRadius: '3px', overflow: 'hidden' } },
          ...SPECTRUM.map((c) => h('div', { style: { display: 'flex', flex: '1', background: c } })))
      : h('div', { style: { display: 'flex', height: '26px' } }),
    text('Исполняемый бенчмарк генерации кода 1С', { fontSize: '38px', color: C.ink3, marginTop: accent === 'line' ? '40px' : '18px' }),
    // подвал: организация и адрес сайта
    h('div', { style: { display: 'flex', alignItems: 'center', gap: '18px', position: 'absolute', bottom: '48px', fontSize: '26px' } },
      text('genlab-1c', { color: C.ink4 }),
      text('·', { color: C.ink4 }),
      text('prism.genlab-1c.ru', { color: C.brand }),
    ),
  );
}

const render = async (node) => sharp(Buffer.from(await satori(node, { width: W, height: H, fonts: FONT_SET }))).png().toBuffer();

if (process.argv.includes('--variants')) {
  const dir = path.join(REPO, 'work', 'social');
  fs.mkdirSync(dir, { recursive: true });
  for (const accent of ['none', 'line']) {
    const out = path.join(dir, `social-${accent}.png`);
    fs.writeFileSync(out, await render(layout({ accent })));
    console.log(`✓ ${path.relative(REPO, out)}`);
  }
} else {
  const png = await render(layout({ accent: 'line' }));
  const out = path.join(REPO, 'docs', 'assets', 'social-preview.png');
  fs.writeFileSync(out, png);
  console.log(`✓ ${path.relative(REPO, out)} — ${W}×${H}, ${(png.length / 1024).toFixed(0)} КБ`);
}
