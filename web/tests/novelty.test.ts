import assert from 'node:assert/strict';
import { test } from 'node:test';

import { byNovelty, firstSeenMs } from '../src/lib/utils/novelty.ts';
import type { Deal } from '../src/lib/types.ts';

function deal(first_seen?: string | null): Pick<Deal, 'product'> {
	return { product: { shop: 'mechta', sku: '1', title: 'x', price: 1, url: '#', in_stock: true, first_seen } };
}

test('firstSeenMs парсит дату среза', () => {
	assert.equal(firstSeenMs(deal('2026-10-03T17:21:35+00:00')), Date.parse('2026-10-03T17:21:35+00:00'));
});

test('firstSeenMs без даты или с мусором — 0 (самое старое)', () => {
	assert.equal(firstSeenMs(deal(null)), 0);
	assert.equal(firstSeenMs(deal(undefined)), 0);
	assert.equal(firstSeenMs(deal('не дата')), 0);
});

test('byNovelty: новые выше, старые и без даты — в конце', () => {
	const fresh = deal('2026-10-03T10:00:00+00:00');
	const older = deal('2026-09-01T10:00:00+00:00');
	const unknown = deal(null);
	assert.ok(byNovelty(fresh, older) < 0, 'новый должен идти раньше старого');
	assert.ok(byNovelty(unknown, fresh) > 0, 'без даты — позже нового');
	assert.ok(byNovelty(older, unknown) < 0, 'старый — раньше позиции без даты');
	assert.equal(byNovelty(fresh, deal('2026-10-03T10:00:00+00:00')), 0);
});
