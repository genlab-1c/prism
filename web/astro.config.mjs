// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';

// Витрина PRISM. Статика + React-островки. Бэкенд не нужен.
// site — адрес деплоя: нужен для АБСОЛЮТНЫХ ссылок canonical/OG (превью в соцсетях)
// и для sitemap. Для GitHub Pages в подпуть добавить ещё base: '/<repo>/'.
// sitemap() генерит sitemap-index.xml + sitemap-0.xml по всем собранным страницам —
// на него ссылается public/robots.txt (карта для Google/Yandex).
export default defineConfig({
  site: 'https://prism.genlab-1c.ru',
  integrations: [react(), sitemap()],
});
