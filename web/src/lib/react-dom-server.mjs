// Прослойка для серверного рендера: отдаёт браузерную сборку react-dom/server вместо
// Node-сборки (зачем — см. комментарий у alias в astro.config.mjs). Сборка написана на
// CommonJS, поэтому грузим её через createRequire: напрямую Vite импортирует её как
// ES-модуль и падает на require.
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const server = require('react-dom/server.browser');

export default server;
export const { renderToReadableStream, renderToString, renderToStaticMarkup, version } = server;
