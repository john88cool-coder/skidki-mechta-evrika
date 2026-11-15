import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verdictOf, realRank, countVerdicts, isReal, VERDICT_ORDER } from '../src/lib/utils/verdict.ts';

test('pump before discount is its own verdict with the honest percent', () => {
	const v = verdictOf({ drop_pct: 67, fair_discount: 33.3, pump_price: 524990 });
	assert.equal(v.kind, 'pumped');
	assert.equal(v.label, 'Накрутка');
	assert.equal(v.real, 33.3);
	assert.match(v.hint, /524.990/);
	assert.match(v.hint, /−33%/);
});

test('pump price without a real drop stays painted', () => {
	assert.equal(verdictOf({ drop_pct: 67, fair_discount: 0, pump_price: 524990 }).kind, 'painted');
	assert.equal(verdictOf({ drop_pct: 67, fair_discount: null, pump_price: 524990 }).kind, 'unknown');
});

test('pumped counts as a real drop and is ranked by the honest percent', () => {
	assert.equal(isReal('pumped'), true);
	assert.equal(isReal('painted'), false);
	assert.equal(isReal('unknown'), false);
	const pumped = { drop_pct: 67, fair_discount: 33, pump_price: 524990 };
	const honest = { drop_pct: 45, fair_discount: 40 };
	assert.ok(realRank(honest) > realRank(pumped));
	assert.ok(realRank(pumped) > realRank({ drop_pct: 80, fair_discount: 0 }));
});

test('countVerdicts covers every verdict kind', () => {
	const counts = countVerdicts([
		{ drop_pct: 67, fair_discount: 33, pump_price: 500000 },
		{ drop_pct: 30, fair_discount: 25 }
	]);
	assert.deepEqual(Object.keys(counts).sort(), [...VERDICT_ORDER].sort());
	assert.equal(counts.pumped, 1);
	assert.equal(counts.honest, 1);
});
