import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verdictOf, realRank, countVerdicts } from '../src/lib/utils/verdict.ts';

test('one verdict per deal from export fields', () => {
	assert.equal(verdictOf({ drop_pct: 30, fair_discount: 25 }).kind, 'honest');
	assert.equal(verdictOf({ drop_pct: 83, fair_discount: 28 }).kind, 'inflated');
	assert.equal(verdictOf({ drop_pct: 81, fair_discount: 0 }).kind, 'painted');
	assert.equal(verdictOf({ drop_pct: 40, fair_discount: null }).kind, 'unknown');
	assert.equal(verdictOf({ drop_pct: 40 }).kind, 'unknown');
});

test('inflated hint states both numbers', () => {
	assert.match(verdictOf({ drop_pct: 83, fair_discount: 28 }).hint, /28%.*−83%/);
});

test('real rank puts confirmed drops first and painted last', () => {
	const deals = [
		{ id: 'painted', drop_pct: 90, fair_discount: 0 },
		{ id: 'unknown', drop_pct: 60, fair_discount: null },
		{ id: 'small', drop_pct: 20, fair_discount: 15 },
		{ id: 'big', drop_pct: 70, fair_discount: 40 }
	];
	const order = [...deals].sort((a, b) => realRank(b) - realRank(a)).map((d) => d.id);
	assert.deepEqual(order, ['big', 'small', 'unknown', 'painted']);
});

test('counts', () => {
	assert.deepEqual(countVerdicts([{ drop_pct: 50, fair_discount: 0 }, { drop_pct: 20, fair_discount: 18 }]),
		{ honest: 1, inflated: 0, painted: 1, unknown: 0 });
});
