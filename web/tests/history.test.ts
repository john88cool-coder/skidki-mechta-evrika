import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recentPrices, formatChange } from '../src/lib/utils/history.ts';

const points = (prices: number[]) => prices.map((price, i) => ({ date: `2026-09-${10 + i}`, price }));

test('latest five retain the previous baseline, including price increases and unchanged prices', () => {
	const result = recentPrices(points([100, 80, 80, 100, 50, 75, 60]));
	assert.deepEqual(result.map(p => p.price), [80, 100, 50, 75, 60]);
	assert.deepEqual(result.map(p => p.change), [0, 25, -50, 50, -20]);
});

test('short or missing history does not invent observations', () => {
	assert.deepEqual(recentPrices([]), []);
	assert.deepEqual(recentPrices(points([100])).map(p => p.change), [null]);
	assert.deepEqual(recentPrices(points([100, 90])).map(p => p.change), [null, -10]);
});

test('bad values cannot produce infinite or NaN percentages', () => {
	assert.deepEqual(recentPrices(points([0, NaN, 100, -1, 50])).map(p => p.change), [null, -50]);
});

test('format differentiates discounts, rises, no change and missing baseline', () => {
	assert.equal(formatChange(null), '—');
	assert.equal(formatChange(0), '0%');
	assert.equal(formatChange(-12.34), '−12,3%');
	assert.equal(formatChange(5), '+5%');
	assert.equal(formatChange(-0.001), '−<0,1%');
});
