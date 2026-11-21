import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dealCard = fs.readFileSync(path.join(root, 'src/lib/components/DealCard.svelte'), 'utf8');
const dealsPage = fs.readFileSync(path.join(root, 'src/routes/deals/+page.svelte'), 'utf8');

function cssRule(source: string, selector: string): string {
	const start = source.indexOf(`${selector} {`);
	assert.ok(start >= 0, `нет правила ${selector}`);
	const end = source.indexOf('}', start);
	assert.ok(end > start, `правило ${selector} не закрыто`);
	return source.slice(start, end);
}

test('видимая подпись скидки не мельче 12px', () => {
	const body = cssRule(dealCard, '.dc-pill small');
	const size = body.match(/font-size:\s*(\d+(?:\.\d+)?)px/);
	assert.ok(size, 'в desktop-правиле .dc-pill small нет font-size в px');
	assert.ok(Number(size[1]) >= 12, `подпись скидки: ${size[1]}px вместо минимум 12px`);
});

test('активные дополнительные фильтры из URL раскрывают панель при входе', () => {
	const extraCount = dealsPage.indexOf('let extraCount = $derived(');
	const moreOpen = dealsPage.indexOf('let moreOpen = $state(untrack(() => extraCount) > 0);');
	assert.ok(extraCount >= 0, 'не найден $derived extraCount');
	assert.ok(
		moreOpen > extraCount,
		'moreOpen должен объявляться после extraCount и открываться только при начальном extraCount > 0'
	);
});
