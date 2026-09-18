// Данные панели грузятся на клиенте из статических JSON (web/static/data),
// которые пересобирает обход: SSR не нужен, страница — оболочка SPA.
export const ssr = false;
export const prerender = true;
export const trailingSlash = 'ignore';