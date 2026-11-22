import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	MIN_COVERAGE_DAYS,
	itemBackHref,
	loadItemCard,
	priceViewOf,
	type ItemDeps
} from '../src/lib/utils/history.ts';
import { verdictOf } from '../src/lib/utils/verdict.ts';
import type { CatalogIndex, CatalogRow, Deal, HistoryRow, Product, ProductHistory } from '../src/lib/types.ts';

const product = (over: Partial<Product> = {}): Product => ({
	shop: 'mechta',
	sku: 'A:17',
	title: 'Demo Phone',
	price: 120000,
	url: 'https://mechta.kz/item/a17',
	in_stock: true,
	...over
});

const row = (over: Partial<CatalogRow> = {}): CatalogRow => ({
	product: product(),
	last_seen: '2026-11-21T10:00:00Z',
	base_price: 120000,
	fair_discount: null,
	pump_price: null,
	exact_model: null,
	...over
});

const historyRow = (over: Partial<HistoryRow> = {}): HistoryRow => ({
	points: [
		{ date: '2026-11-15', price: 120000 },
		{ date: '2026-11-18', price: 120000 },
		{ date: '2026-11-21', price: 120000 }
	],
	recent_points: [{ date: '2026-11-21T10:00:00Z', price: 120000, old_price: null }],
	min: 120000,
	median: 120000,
	days_at_current: 3,
	coverage_days: 7,
	...over
});

const deal = (over: Partial<Deal> = {}): Deal => ({
	product: product({ price: 120000, old_price: 150000 }),
	signal: 'deal',
	drop_pct: 20,
	base_price: 150000,
	pump_price: null,
	fair_discount: 20,
	...over
});

const emptyDeps = (over: Partial<ItemDeps> = {}): ItemDeps => ({
	loader: { loadIndex: async () => null, loadHistory: async () => null },
	fetchHistory: async () => null,
	snapshot: () => null,
	...over
});

test('found: точная пара даёт реальные title, url, price и last_seen; история может быть пустой', async () => {
	const deps = emptyDeps({
		loader: {
			loadIndex: async () => ({ schema: 2, shop: 'mechta', rows: [row()] }) satisfies CatalogIndex,
			loadHistory: async () => null
		}
	});
	const res = await loadItemCard(deps, 'mechta', 'A:17');
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.product.title, 'Demo Phone');
	assert.equal(res.card.product.price, 120000);
	assert.equal(res.card.product.url, 'https://mechta.kz/item/a17');
	assert.equal(res.card.lastSeen, '2026-11-21T10:00:00Z');
	assert.equal(res.card.source, 'catalog-v2');
	assert.deepEqual(res.card.points, []);
	assert.equal(res.card.basePrice, 120000);
});

test('missing: пары нет ни в индексе, ни в старом срезе, ни в избранном', async () => {
	const deps = emptyDeps({
		loader: { loadIndex: async () => ({ schema: 2, shop: 'mechta', rows: [] }), loadHistory: async () => null }
	});
	const res = await loadItemCard(deps, 'mechta', 'NOPE');
	assert.equal(res.status, 'missing');
});

test('unavailable: сбой сети — товар можно запросить повторно', async () => {
	let fail = true;
	let calls = 0;
	const deps = emptyDeps({
		loader: {
			loadIndex: async () => {
				calls += 1;
				if (fail) throw new Error('HTTP 503');
				return { schema: 2, shop: 'mechta', rows: [row()] };
			},
			loadHistory: async () => null
		}
	});
	const first = await loadItemCard(deps, 'mechta', 'A:17');
	if (first.status !== 'unavailable') assert.fail(`ожидается unavailable, получено ${first.status}`);
	assert.match(first.reason, /503/);
	fail = false;
	const second = await loadItemCard(deps, 'mechta', 'A:17');
	assert.equal(second.status, 'found');
	assert.equal(calls, 2);
});

test('старый срез: fetchHistory поставляет карточку, база — median 30д', async () => {
	const legacy: ProductHistory = {
		product: product({ price: 110000 }),
		history: [
			{ date: '2026-11-17', price: 110000 },
			{ date: '2026-11-19', price: 110000 },
			{ date: '2026-11-21', price: 110000 }
		],
		recent: [{ date: '2026-11-21', price: 110000 }],
		stats: { min_90d: 110000, median_30d: 120000, days_at_current: 1 }
	};
	const deps = emptyDeps({ fetchHistory: async () => legacy });
	const res = await loadItemCard(deps, 'mechta', 'A:17');
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.source, 'legacy');
	assert.equal(res.card.basePrice, 120000);
	assert.equal(res.card.stats?.min90d, 110000);
	assert.equal(res.card.coverageDays, 5);
});

test('сохранённая копия избранного выручает, когда товара нет нигде', async () => {
	const deps = emptyDeps({
		snapshot: (id) => (id === 'mechta:A:17' ? product({ price: 99000 }) : null)
	});
	const res = await loadItemCard(deps, 'mechta', 'A:17');
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.source, 'favorites');
	assert.equal(res.card.product.price, 99000);
	assert.deepEqual(res.card.points, []);
});

test('гонка A → B: устаревший ответ отбрасывается, активная пара применяется', async () => {
	let releaseA: (() => void) | undefined;
	const gate = new Promise<void>((resolve) => {
		releaseA = resolve;
	});
	const indexA: CatalogIndex = {
		schema: 2,
		shop: 'a',
		rows: [row({ product: product({ shop: 'a', sku: '1', title: 'Товар A', price: 1000 }) })]
	};
	const indexB: CatalogIndex = {
		schema: 2,
		shop: 'b',
		rows: [row({ product: product({ shop: 'b', sku: '2', title: 'Товар B', price: 2000 }) })]
	};
	const deps = emptyDeps({
		loader: {
			loadIndex: async (shop) => {
				if (shop === 'a') {
					await gate;
					return indexA;
				}
				return indexB;
			},
			loadHistory: async () => null
		}
	});
	let aActive = true;
	const pendingA = loadItemCard(deps, 'a', '1', () => aActive);
	aActive = false; // быстрый переход A → B: пара A больше не активна
	const b = await loadItemCard(deps, 'b', '2', () => true);
	if (b.status !== 'found') assert.fail(`ожидается found для B, получено ${b.status}`);
	assert.equal(b.card.product.title, 'Товар B');
	releaseA!();
	const a = await pendingA;
	assert.equal(a.status, 'stale');
});

test('SKU с :, /, % и Unicode совпадает точно', async () => {
	const weird = 'a:b/c%d⭐';
	const deps = emptyDeps({
		loader: {
			loadIndex: async () => ({
				schema: 2,
				shop: 'mechta',
				rows: [row({ product: product({ sku: weird, title: 'Weird SKU', price: 5000 }) })]
			}),
			loadHistory: async (_shop, sku) =>
				sku === weird
					? historyRow({
							points: [{ date: '2026-11-21', price: 5000 }],
							recent_points: [],
							min: 5000,
							median: 5000,
							days_at_current: 0,
							coverage_days: 1
						})
					: null
		}
	});
	const res = await loadItemCard(deps, 'mechta', weird);
	if (res.status !== 'found') assert.fail(`ожидается found, получено ${res.status}`);
	assert.equal(res.card.product.title, 'Weird SKU');
	assert.equal(res.card.points.length, 1);
});

test('view model: позиция со скидкой использует те же входные данные и verdictOf, что на витрине', () => {
	const d = deal();
	const view = priceViewOf({
		price: d.product.price ?? null,
		basePrice: null,
		coverageDays: 10,
		available: true,
		deal: d
	});
	assert.equal(view.kind, 'deal');
	assert.deepEqual(view.verdict, verdictOf(d));
	assert.equal(view.label, verdictOf(d).label);
});

test('view model: цена 120000 при базе 120000 — «На уровне обычной цены»', () => {
	const view = priceViewOf({ price: 120000, basePrice: 120000, coverageDays: 10, available: true, deal: null });
	assert.equal(view.kind, 'flat');
	assert.equal(view.label, 'На уровне обычной цены');
	assert.equal(view.deviation, 0);
});

test('view model: отклонение в тенге ниже и выше базы', () => {
	const below = priceViewOf({ price: 110000, basePrice: 120000, coverageDays: 10, available: true, deal: null });
	assert.equal(below.kind, 'below');
	assert.equal(below.deviation, 10000);
	assert.ok(below.percent !== null && Math.round(below.percent) === 8);
	const above = priceViewOf({ price: 130000, basePrice: 120000, coverageDays: 10, available: true, deal: null });
	assert.equal(above.kind, 'above');
	assert.equal(above.deviation, -10000);
});

test(`view model: недостаточная история — «Пока мало истории» и дата начала наблюдений`, () => {
	const thin = priceViewOf({
		price: 120000,
		basePrice: 130000,
		coverageDays: MIN_COVERAGE_DAYS - 1,
		firstSeen: '2026-11-20',
		available: true,
		deal: null
	});
	assert.equal(thin.kind, 'thin-history');
	assert.equal(thin.label, 'Пока мало истории');
	assert.equal(thin.firstSeen, '2026-11-20');
	const none = priceViewOf({ price: 120000, basePrice: null, coverageDays: null, available: true, deal: null });
	assert.equal(none.kind, 'thin-history');
	assert.equal(none.firstSeen, null);
});

test('view model: неизвестная база — процент экономии отсутствует', () => {
	const view = priceViewOf({ price: 120000, basePrice: null, coverageDays: 10, available: true, deal: null });
	assert.equal(view.kind, 'no-base');
	assert.equal(view.basePrice, null);
	assert.equal(view.percent, null);
});

test('view model: выбывший товар подписан датой последнего наблюдения', () => {
	const view = priceViewOf({
		price: 99000,
		basePrice: 120000,
		coverageDays: 30,
		lastSeen: '2026-11-01T00:00:00Z',
		available: false,
		deal: null
	});
	assert.equal(view.kind, 'delisted');
	assert.equal(view.lastSeen, '2026-11-01T00:00:00Z');
});

test('одинаковая база Stage 1/v2: обе дороги дают одну базу и один вывод', async () => {
	const v2 = await loadItemCard(
		emptyDeps({
			loader: {
				loadIndex: async () => ({ schema: 2, shop: 'mechta', rows: [row({ base_price: 120000 })] }),
				loadHistory: async () => historyRow()
			}
		}),
		'mechta',
		'A:17'
	);
	const legacy = await loadItemCard(
		emptyDeps({
			fetchHistory: async () => ({
				product: product(),
				history: [
					{ date: '2026-11-17', price: 120000 },
					{ date: '2026-11-19', price: 120000 },
					{ date: '2026-11-21', price: 120000 }
				],
				stats: { min_90d: 120000, median_30d: 120000, days_at_current: 3 }
			})
		}),
		'mechta',
		'A:17'
	);
	if (v2.status !== 'found' || legacy.status !== 'found') assert.fail('обе дороги должны найти товар');
	assert.equal(v2.card.basePrice, legacy.card.basePrice);
	const v2View = priceViewOf({
		price: 120000,
		basePrice: v2.card.basePrice,
		coverageDays: v2.card.coverageDays,
		available: true,
		deal: null
	});
	const legacyView = priceViewOf({
		price: 120000,
		basePrice: legacy.card.basePrice,
		coverageDays: legacy.card.coverageDays,
		available: true,
		deal: null
	});
	assert.equal(v2View.kind, legacyView.kind);
	assert.equal(v2View.label, legacyView.label);
	assert.equal(v2View.label, 'На уровне обычной цены');
});

test('возврат: только явные пути /, /deals, /search под base; внешние ведут к каталогу', () => {
	const base = '/skidki';
	const origin = 'https://app.test';
	assert.equal(itemBackHref(`${base}/deals`, base, origin), `${base}/deals`);
	assert.equal(itemBackHref(`${base}/search?q=demo+phone`, base, origin), `${base}/search?q=demo+phone`);
	assert.equal(itemBackHref(`${base}/`, base, origin), `${base}/`);
	assert.equal(itemBackHref('https://evil.example', base, origin), `${base}/deals`);
	assert.equal(itemBackHref(`${base}/favorites`, base, origin), `${base}/deals`);
	assert.equal(itemBackHref('//other.example', '', origin), '/deals');
	assert.equal(itemBackHref('https://evil.example', '', origin), '/deals');
	assert.equal(itemBackHref(null, '', origin), '/deals');
	assert.equal(itemBackHref('/deals', '', origin), '/deals');
	assert.equal(itemBackHref('/search?q=x', '', origin), '/search?q=x');
	assert.equal(itemBackHref('/other', '', origin), '/deals');
});
