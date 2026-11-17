import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dailyPrices, sparkline } from '../src/lib/utils/sparkline.ts';
import { NAV_ITEMS, isActive } from '../src/lib/utils/nav.ts';
import { countExtraFilters } from '../src/lib/utils/filters.ts';
import { relatedDeals } from '../src/lib/utils/related.ts';

test('dailyPrices keeps the last price per day, in date order', () => {
	assert.deepEqual(
		dailyPrices([
			{ date: '2026-11-02', price: 200 },
			{ date: '2026-11-01', price: 100 },
			{ date: '2026-11-02', price: 150 },
			{ date: '2026-11-03', price: 0 }
		]),
		[100, 150]
	);
});

test('sparkline draws a step line inside the box and reports the trend', () => {
	const s = sparkline(
		[
			{ date: '2026-11-01', price: 300 },
			{ date: '2026-11-02', price: 500 },
			{ date: '2026-11-03', price: 200 }
		],
		100,
		20,
		0
	);
	assert.ok(s);
	assert.equal(s.line, 'M0 13.3 H50 V0 H100 V20');
	assert.equal(s.area, 'M0 13.3 H50 V0 H100 V20 V20 H0 Z');
	assert.equal(s.trend, 'down');
	assert.equal(s.days, 3);
});

test('sparkline needs two days and draws a flat price in the middle', () => {
	assert.equal(sparkline([{ date: '2026-11-01', price: 100 }]), null);
	const flat = sparkline([{ date: '2026-11-01', price: 100 }, { date: '2026-11-05', price: 100 }], 100, 20, 0);
	assert.ok(flat);
	assert.equal(flat.trend, 'flat');
	assert.equal(flat.line, 'M0 10 H100 V10');
	const up = sparkline([{ date: '2026-11-01', price: 100 }, { date: '2026-11-05', price: 120 }]);
	assert.equal(up?.trend, 'up');
});

test('navigation has four sections without the removed Top and Compare pages', () => {
	assert.deepEqual(NAV_ITEMS.map((i) => i.path), ['/', '/deals', '/shops', '/favorites']);
});

test('isActive matches the section and its subpages, home only itself', () => {
	const base = '/skidki-mechta-evrika';
	assert.equal(isActive(`${base}/`, '/', base), true);
	assert.equal(isActive(base, '/', base), true);
	assert.equal(isActive(`${base}/deals`, '/', base), false);
	assert.equal(isActive(`${base}/deals`, '/deals', base), true);
	assert.equal(isActive(`${base}/deals/`, '/deals', base), true);
	assert.equal(isActive(`${base}/dealsx`, '/deals', base), false);
	assert.equal(isActive('/', '/', ''), true);
	assert.equal(isActive('/shops', '/shops', ''), true);
	assert.equal(isActive('/item', '/deals', ''), false);
});

test('countExtraFilters counts only the hidden filters that are on', () => {
	const none = { shop: 'all', group: 'all', brand: 'all', minPct: 0, priceMax: 'all', inStockOnly: false, favOnly: false };
	assert.equal(countExtraFilters(none), 0);
	assert.equal(countExtraFilters({ ...none, shop: 'mechta', minPct: 20, favOnly: true }), 3);
});

const deal = (sku: string, price: number, group: string, category: string, fair: number | null = null) => ({
	product: { shop: 's', sku, title: sku, price, url: '#', in_stock: true, group, category },
	signal: 'deal' as const,
	drop_pct: 30,
	fair_discount: fair
});

test('relatedDeals: same group and similar price, same category first, real drops first', () => {
	const laptop = deal('target', 200_000, 'computers', 'Ноутбуки');
	const all = [
		laptop,
		deal('keyboard', 25_000, 'computers', 'Клавиатуры', 20),
		deal('monitor', 150_000, 'computers', 'Мониторы', 30),
		deal('laptop-cheap', 120_000, 'computers', 'Ноутбуки'),
		deal('laptop-real', 260_000, 'computers', 'Ноутбуки', 15),
		deal('laptop-far', 900_000, 'computers', 'Ноутбуки', 40),
		deal('tv', 200_000, 'tv', 'Телевизоры', 50)
	];
	assert.deepEqual(relatedDeals(laptop, all).map((d) => d.product.sku), ['laptop-real', 'laptop-cheap', 'monitor']);
	assert.deepEqual(relatedDeals(laptop, all, 1).map((d) => d.product.sku), ['laptop-real']);
});
