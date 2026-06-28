// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// Витрина PRISM. Статика + React-островки. Бэкенд не нужен.
// site/base пригодятся при деплое на GitHub Pages в подпуть — выставить тогда.
export default defineConfig({
  integrations: [react()],
});
