import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildFallbackProduct, computeDaysAtCurrent } from '../src/lib/utils/history.ts';

test('computeDaysAtCurrent counts continuous days at the latest price instead of array length', () => {
	const now = Date.parse('2026-11-12T12:00:00Z');
	const points = [
		{ date: '2026-11-01', price: 250_000 },
		{ date: '2026-11-05', price: 250_000 },
		{ date: '2026-11-09', price: 199_990 },
		{ date: '2026-11-11', price: 199_990 },
		{ date: '2026-11-12', price: 199_990 }
	];
	// Текущая цена 199 990 держится непрерывно с 2026-11-09 (3 полных дня до 2026-11-12T12:00Z), а не 5 точек!
	assert.equal(computeDaysAtCurrent(points, now), 3);
});

test('buildFallbackProduct reuses saved snapshot metadata and avoids dead "#" url when missing', () => {
	const points = [
		{ date: '2026-11-10', price: 320_000, old_price: 380_000 },
		{ date: '2026-11-12', price: 310_000, old_price: 350_000 }
	];
	const withSnap = buildFallbackProduct('mechta', '77', points, {
		shop: 'mechta',
		sku: '77',
		title: 'Телевизор LG OLED C4',
		price: 299_990,
		url: 'https://www.mechta.kz/product/lg-c4/',
		brand: 'LG',
		in_stock: true,
		rating: 4.9,
		reviews_count: 31
	});
	assert.equal(withSnap.title, 'Телевизор LG OLED C4');
	assert.equal(withSnap.price, 310_000);
	assert.equal(withSnap.old_price, 350_000);
	assert.equal(withSnap.url, 'https://www.mechta.kz/product/lg-c4/');
	assert.equal(withSnap.rating, 4.9);

	const noSnap = buildFallbackProduct('evrika', '99', points, null);
	assert.equal(noSnap.title, 'evrika · 99');
	assert.equal(noSnap.url, '');
});
