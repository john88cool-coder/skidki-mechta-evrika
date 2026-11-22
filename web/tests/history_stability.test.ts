import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	MIN_COVERAGE_DAYS,
	coverageFromRow,
	loadItemCard,
	priceViewOf,
	type ItemDeps
} from '../src/lib/utils/history.ts';
import type { CatalogIndex, HistoryRow } from '../src/lib/types.ts';

const product = () => ({
	shop: 'mechta',
	sku: 'A:17',
	title: 'Demo Phone',
	price: 120000,
	url: 'https://mechta.kz/item/a17',
	in_stock: true
});

const row = () => ({
	product: product(),
	last_seen: '2026-11-21T10:00:00Z',
	base_price: 120000,
	fair_discount: null,
	pump_price: null,
	exact_model: null
});

/** Новое поколение файлов: first_stocked вместо числового coverage_days. */
const freshRow = (over: Partial<HistoryRow> = {}): HistoryRow => ({
	points: [
		{ date: '2026-11-18', price: 120000 },
		{ date: '2026-11-21', price: 120000 }
	],
	recent_points: [{ date: '2026-11-21T10:00:00Z', price: 120000 }],
	min: 120000,
	median: 120000,
	days_at_current: 3,
	first_stocked: '2026-11-14T10:00:00Z',
	...over
});

const itemDeps = (loader: Partial<ItemDeps['loader']> = {}): ItemDeps => ({
	loader: {
		loadIndex: async () => ({ schema: 2, shop: 'mechta', rows: [row()] }) satisfies CatalogIndex,
		loadHistory: async () => freshRow(),
		getSource: async () => ({ last_crawl: '2026-11-21T10:00:00Z' }),
		...loader
	},
	fetchHistory: async () => null,
	snapshot: () => null
});

test('порог трёх суток — точные часы: 71:59 мало, 72:00 достаточно', () => {
	const history = freshRow({ first_stocked: '2026-11-18T00:00:00Z' });
	const cov71 = coverageFromRow(history, '2026-11-20T23:59:00Z'); // 71 ч 59 мин
	const cov72 = coverageFromRow(history, '2026-11-21T00:00:00Z'); // 72 ч
	assert.ok(cov71 !== null && cov71 > MIN_COVERAGE_DAYS - 1 / 24 && cov71 < MIN_COVERAGE_DAYS);
	assert.equal(cov72, MIN_COVERAGE_DAYS);
	const thin = priceViewOf({ price: 120000, basePrice: 130000, coverageDays: cov71, available: true, deal: null });
	assert.equal(thin.kind, 'thin-history');
	assert.equal(thin.label, 'Пока мало истории');
	const enough = priceViewOf({ price: 120000, basePrice: 130000, coverageDays: cov72, available: true, deal: null });
	assert.equal(enough.kind, 'below');
	assert.equal(enough.label, 'Ниже обычной цены');
});

test('покрытие карточки — от времени оценки среза (last_crawl источника), не от часов браузера', async () => {
	const res = await loadItemCard(
		itemDeps({
			loadHistory: async () => freshRow({ first_stocked: '2026-11-18T00:00:00Z' }),
			getSource: async () => ({ last_crawl: '2026-11-21T00:00:00Z' })
		}),
		'mechta',
		'A:17'
	);
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	// Ровно 72 часа от метки среза, а не от Date.now(): 2026-11-22 в браузере дало бы ~4.
	assert.equal(res.card.coverageDays, 3);
	assert.equal(res.card.firstStocked, '2026-11-18');
});

test('coverageFromRow: новые файлы — точные часы; старые — готовое число', () => {
	const fresh = freshRow({ first_stocked: '2026-11-18T00:00:00Z' });
	assert.equal(coverageFromRow(fresh, '2026-11-21T00:00:00Z'), 3);
	assert.equal(coverageFromRow(fresh, null), null);
	assert.equal(coverageFromRow(freshRow({ first_stocked: null }), '2026-11-21T00:00:00Z'), null);
	const legacy: HistoryRow = { ...freshRow(), first_stocked: undefined, coverage_days: 7 };
	assert.equal(coverageFromRow(legacy, null), 7);
	assert.equal(coverageFromRow(null, '2026-11-21T00:00:00Z'), null);
});

test('старые файлы: числовой coverage_days читается как раньше', async () => {
	const legacy: HistoryRow = { ...freshRow(), first_stocked: undefined, coverage_days: 7 };
	const res = await loadItemCard(
		itemDeps({ loadHistory: async () => legacy, getSource: async () => null }),
		'mechta',
		'A:17'
	);
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.coverageDays, 7);
	assert.equal(res.card.firstStocked, null);
	const view = priceViewOf({ price: 120000, basePrice: 130000, coverageDays: res.card.coverageDays, available: true, deal: null });
	assert.equal(view.kind, 'below');
});

test('нет наблюдений в наличии — first_stocked null даёт «Пока мало истории»', async () => {
	const res = await loadItemCard(
		itemDeps({ loadHistory: async () => freshRow({ first_stocked: null, points: [], recent_points: [] }) }),
		'mechta',
		'A:17'
	);
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.coverageDays, null);
	const view = priceViewOf({ price: 120000, basePrice: 130000, coverageDays: res.card.coverageDays, available: true, deal: null });
	assert.equal(view.kind, 'thin-history');
	assert.equal(view.label, 'Пока мало истории');
});

test('источник без метки last_crawl — покрытие неизвестно, решение консервативно', async () => {
	const res = await loadItemCard(itemDeps({ getSource: async () => null }), 'mechta', 'A:17');
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.coverageDays, null);
	const view = priceViewOf({ price: 120000, basePrice: 130000, coverageDays: res.card.coverageDays, available: true, deal: null });
	assert.equal(view.kind, 'thin-history');
});
