// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';

/* Таблицы из markdown (доки, методология) заворачиваем в скролл-обёртку — тот же приём,
   что TableScroll на лидерборде: на узком экране листается САМА ТАБЛИЦА, а не страница.
   Широким таблицам (3+ колонки) CSS добавит min-width, чтобы колонки не схлопывались;
   узкие («условие | балл») помещаются и так, им скролл не нужен — поэтому считаем колонки. */
function rehypeTableScroll() {
  const countCols = (table) => {
    let cols = 0;
    const findRow = (n) => {
      if (cols || !n) return;
      if (n.type === 'element' && n.tagName === 'tr') {
        cols = n.children.filter((c) => c.type === 'element' && (c.tagName === 'th' || c.tagName === 'td')).length;
        return;
      }
      (n.children || []).forEach(findRow);
    };
    findRow(table);
    return cols;
  };
  return (tree) => {
    const walk = (node) => {
      if (!Array.isArray(node.children)) return;
      node.children.forEach(walk);
      node.children = node.children.map((child) => {
        if (child.type !== 'element' || child.tagName !== 'table') return child;
        const className = ['table-scroll'];
        if (countCols(child) >= 3) className.push('table-scroll--wide');
        return { type: 'element', tagName: 'div', properties: { className }, children: [child] };
      });
    };
    walk(tree);
  };
}

// Витрина PRISM. Статика + React-островки. Бэкенд не нужен.
// site — адрес деплоя: нужен для АБСОЛЮТНЫХ ссылок canonical/OG (превью в соцсетях)
// и для sitemap. Для GitHub Pages в подпуть добавить ещё base: '/<repo>/'.
// sitemap() генерит sitemap-index.xml + sitemap-0.xml по всем собранным страницам —
// на него ссылается public/robots.txt (карта для Google/Yandex).
export default defineConfig({
  site: 'https://prism.genlab-1c.ru',
  integrations: [react(), sitemap()],
  markdown: { rehypePlugins: [rehypeTableScroll] },
});
