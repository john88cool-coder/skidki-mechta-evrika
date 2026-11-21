import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const css = fs.readFileSync(path.join(root, 'src/app.css'), 'utf8');

/** Значения hex-токенов внутри первого блока, начинающегося с `selector {`. */
function tokens(selector: string): Record<string, string> {
	const start = css.indexOf(`${selector} {`);
	assert.ok(start >= 0, `нет блока ${selector}`);
	const body = css.slice(start, css.indexOf('}', start));
	const out: Record<string, string> = {};
	for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2];
	return out;
}

function luminance(hex: string): number {
	const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
	const f = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
	return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrast(a: string, b: string): number {
	const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
	return (x + 0.05) / (y + 0.05);
}

const light = tokens(':root');
const dark = { ...light, ...tokens("html[data-theme='dark']") };

for (const [name, t] of [['светлая', light], ['тёмная', dark]] as const) {
	test(`${name} тема: вторичный текст читается на всех фонах (WCAG AA 4.5:1)`, () => {
		for (const fg of ['ink-2', 'ink-3', 'ink-4']) {
			for (const bg of ['surface', 'paper', 'paper-2']) {
				const ratio = contrast(t[fg], t[bg]);
				assert.ok(ratio >= 4.5, `--${fg} ${t[fg]} на --${bg} ${t[bg]}: ${ratio.toFixed(2)}`);
			}
		}
	});

	test(`${name} тема: цветной текст вердиктов читается на своей подложке`, () => {
		for (const [fg, bg] of [['success', 'success-bg'], ['warn', 'warn-bg'], ['bad', 'bad-bg']]) {
			const ratio = contrast(t[fg], t[bg]);
			assert.ok(ratio >= 4.5, `--${fg} ${t[fg]} на --${bg} ${t[bg]}: ${ratio.toFixed(2)}`);
		}
	});
}
