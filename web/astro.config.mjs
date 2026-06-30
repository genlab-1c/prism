// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// Витрина PRISM. Статика + React-островки. Бэкенд не нужен.
// site — адрес деплоя: нужен для АБСОЛЮТНЫХ ссылок canonical/OG (превью в соцсетях).
// TODO: заменить плейсхолдер на реальный домен перед публикацией. Для GitHub Pages
// в подпуть добавить ещё base: '/<repo>/'.
export default defineConfig({
  site: 'https://prism.genlab-1c.ru',
  integrations: [react()],
});
