import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('package.json does not carry unused icon/UI/adapter packages', () => {
	const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
	const allDeps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
	assert.equal('lucide-svelte' in allDeps, false, 'use @lucide/svelte only');
	assert.equal('daisyui' in allDeps, false, 'daisyui is unused');
	assert.equal('@sveltejs/adapter-auto' in allDeps, false, 'adapter-static is used');
	assert.equal('@lucide/svelte' in allDeps, true);
	assert.equal('@sveltejs/adapter-static' in allDeps, true);
});

test('PriceChart lazy-loads modular echarts/core instead of monolithic echarts barrel', () => {
	const src = fs.readFileSync(path.join(root, 'src/lib/components/PriceChart.svelte'), 'utf8');
	assert.equal(/import\s+\*\s+as\s+echarts\s+from\s+['"]echarts['"]/.test(src), false);
	assert.equal(src.includes("import('echarts/core')"), true);
	assert.equal(src.includes("import('echarts/charts')"), true);
	assert.equal(src.includes("import('echarts/components')"), true);
	assert.equal(src.includes("import('echarts/renderers')"), true);
	assert.equal(src.includes('ResizeObserver'), true);
});
