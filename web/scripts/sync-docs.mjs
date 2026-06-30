/* ============================================================
   PRISM web — синхронизация документации из MkDocs.
   Источник правды — docs/*.md и tasks/README.md (их же рендерит MkDocs).
   Здесь копия в src/content/md/ (заигнорена), с правкой MkDocs-синтаксиса
   под Astro: admonitions (!!! / ???) → блок-цитаты, снятие <div>-обёрток
   и генераторных HTML-комментариев. Контент не меняем — только синтаксис.
   ============================================================ */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const OUT = path.join(HERE, '..', 'src', 'content', 'md');

// Какие документы берём в сайт (slug → файл, заголовок, в каком разделе nav).
// index.md и leaderboard.md не берём: их роль на сайте играет живая главная.
const PAGES = [
  { src: path.join(REPO, 'docs', 'how-it-works.md'), slug: 'how-it-works', title: 'Как это работает', section: 'docs' },
  { src: path.join(REPO, 'docs', 'architecture.md'), slug: 'architecture', title: 'Архитектура', section: 'docs' },
  { src: path.join(REPO, 'docs', 'cli.md'), slug: 'cli', title: 'Как запустить', section: 'docs' },
  { src: path.join(REPO, 'docs', 'status.md'), slug: 'status', title: 'Что умеет сейчас', section: 'docs' },
  { src: path.join(REPO, 'docs', 'validity.md'), slug: 'validity', title: 'Честные границы', section: 'docs' },
  { src: path.join(REPO, 'tasks', 'README.md'), slug: 'tasks', title: 'Банк задач', section: 'tasks' },
];

const ADM = {
  note: 'Заметка', tip: 'Совет', info: 'Инфо', warning: 'Важно', danger: 'Осторожно',
  example: 'Пример', success: 'Готово', question: 'Вопрос', abstract: 'Кратко',
  quote: 'Цитата', bug: 'Баг', failure: 'Провал', caution: 'Осторожно',
};

function transform(src) {
  const lines = src.split('\n');
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // снять <div ...>/</div> обёртки (MkDocs-центрирование таблиц)
    if (/^\s*<\/?div\b[^>]*>\s*$/.test(line)) continue;
    // однострочный HTML-комментарий
    if (/^\s*<!--.*-->\s*$/.test(line)) continue;
    // многострочный HTML-комментарий
    if (/^\s*<!--/.test(line) && !/-->/.test(line)) {
      while (i < lines.length && !/-->/.test(lines[i])) i++;
      continue;
    }

    // admonition: !!! type "Title"  /  ??? type "Title"  → блок-цитата
    const m = line.match(/^(\s*)(?:!!!|\?\?\?\+?)\s+([\w-]+)(?:\s+"([^"]*)")?\s*$/);
    if (m) {
      const indent = m[1].length;
      const type = m[2].toLowerCase();
      const title = m[3] || ADM[type] || (type[0].toUpperCase() + type.slice(1));
      const body = [];
      let j = i + 1;
      for (; j < lines.length; j++) {
        const l = lines[j];
        if (l.trim() === '') { body.push(''); continue; }
        if (l.length - l.trimStart().length > indent) body.push(l.slice(indent + 4));
        else break;
      }
      while (body.length && body[body.length - 1] === '') body.pop();
      out.push(`> **${title}**`, '>');
      for (const b of body) out.push(b === '' ? '>' : `> ${b}`);
      out.push('');
      i = j - 1;
      continue;
    }

    // ссылки на соседние .md → на маршруты сайта (/docs/<slug>), битые якоря убираем хвост .md
    out.push(line.replace(/\]\(([\w./-]+?)\.md(#[\w-]+)?\)/g, (_, p, anchor) => {
      const base = p.split('/').pop();
      const known = PAGES.find((x) => x.slug === base);
      return known ? `](/${known.section === 'tasks' ? 'tasks' : 'docs/' + base}${anchor || ''})` : `](${p}${anchor || ''})`;
    }));
  }
  return out.join('\n');
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
for (const p of PAGES) {
  let raw = fs.readFileSync(p.src, 'utf8');
  // срезать исходный YAML-фронтматтер (иначе утечёт в тело), вытащив из него description для SEO
  let description = '';
  const fmMatch = raw.match(/^---\n([\s\S]*?)\n---\n?/);
  if (fmMatch) {
    const d = fmMatch[1].match(/^description:\s*(.+)$/m);
    if (d) description = d[1].trim().replace(/^["']|["']$/g, '');
    raw = raw.slice(fmMatch[0].length);
  }
  const md = transform(raw);
  const fm = `---\ntitle: ${JSON.stringify(p.title)}\nslug: ${JSON.stringify(p.slug)}\nsection: ${JSON.stringify(p.section)}\n`
    + (description ? `description: ${JSON.stringify(description)}\n` : '')
    + '---\n\n';
  fs.writeFileSync(path.join(OUT, `${p.slug}.md`), fm + md);
}
console.log(`✓ src/content/md — ${PAGES.length} страниц из docs/ + tasks (admonitions → цитаты)`);
