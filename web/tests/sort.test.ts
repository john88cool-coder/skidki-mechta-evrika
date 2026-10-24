import assert from 'node:assert/strict';
import { test } from 'node:test';

import { bySortKey, SORT_LABELS, type SortKey } from '../src/lib/utils/sort.ts';
import type { Deal } from '../src/lib/types.ts';

function deal(partial: Partial<Deal['product']> & Pick<Deal['product'], 'title' | 'price'>, extra: Partial<Deal> = {}): Deal {
	return {
		product: { shop: 'mechta', sku: Math.random().toString(36).slice(2), url: '#', in_stock: true, ...partial },
		signal: 'deal',
		...extra
	};
}

test('SORT_LABELS покрывает все ключи, включая «Сначала новинки»', () => {
	const keys: SortKey[] = ['real', 'new', 'claimed', 'price', 'price_desc', 'title'];
	for (const key of keys) assert.ok(SORT_LABELS[key], `нет подписи для ${key}`);
});

test('new: новые товары выше, без даты — в конце', () => {
	const fresh = deal({ title: 'x', price: 1, first_seen: '2026-10-20T00:00:00+00:00' });
	const older = deal({ title: 'y', price: 1, first_seen: '2026-09-01T00:00:00+00:00' });
	const unknown = deal({ title: 'z', price: 1 });
	const sorted = [unknown, older, fresh].sort(bySortKey('new'));
	assert.deepEqual(sorted.map((d) => d.product.title), ['x', 'y', 'z']);
});

test('price / price_desc: по возрастанию и убыванию цены', () => {
	const cheap = deal({ title: 'cheap', price: 100 });
	const pricey = deal({ title: 'pricey', price: 900 });
	assert.deepEqual([pricey, cheap].sort(bySortKey('price')).map((d) => d.product.price), [100, 900]);
	assert.deepEqual([cheap, pricey].sort(bySortKey('price_desc')).map((d) => d.product.price), [900, 100]);
});

test('claimed: глубже заявленная скидка — выше', () => {
	const small = deal({ title: 'small', price: 1 }, { drop_pct: 10 });
	const big = deal({ title: 'big', price: 1 }, { drop_pct: 45 });
	assert.deepEqual([small, big].sort(bySortKey('claimed')).map((d) => d.drop_pct), [45, 10]);
});

test('real: подтверждённое снижение выше нарисованной скидки', () => {
	const honest = deal({ title: 'honest', price: 1 }, { drop_pct: 20, fair_discount: 18 });
	const painted = deal({ title: 'painted', price: 1 }, { drop_pct: 60, fair_discount: 0 });
	const sorted = [painted, honest].sort(bySortKey('real'));
	assert.equal(sorted[0].product.title, 'honest');
});

test('title: сортировка по названию в русской локали', () => {
	const a = deal({ title: 'Яблоко', price: 1 });
	const b = deal({ title: 'Арбуз', price: 1 });
	assert.deepEqual([a, b].sort(bySortKey('title')).map((d) => d.product.title), ['Арбуз', 'Яблоко']);
});
