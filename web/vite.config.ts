import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// GitHub Pages отдаёт проект по /<repo>/, поэтому base задаётся из окружения
// в workflow (BASE_PATH=/skidki-mechta-evrika). Локально base пустой.
// Тип SvelteKit требует либо '', либо путь, начинающийся со слэша.
function resolveBase(): '' | `/${string}` {
  const raw = process.env.BASE_PATH ?? '';
  if (!raw) return '';
  // Git Bash on Windows rewrites "/skidki-..." to "C:/Program Files/Git/skidki-..."
  // via MSYS path conversion; recover the intended base.
  const idx = raw.indexOf('/skidki');
  const normalized = idx >= 0 ? raw.slice(idx) : raw;
  return normalized as '' | `/${string}`;
}
const base = resolveBase();

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			paths: { base },
			adapter: adapter({
				pages: 'build',
				assets: 'build',
				fallback: 'index.html',
				precompress: false,
				strict: true
			})
		})
	]
});
