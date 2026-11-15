import { test } from 'node:test';
import assert from 'node:assert/strict';
import { baseDelta } from '../src/lib/utils/history.ts';

test('baseDelta measures the saving from the usual price only', () => {
	assert.deepEqual(baseDelta(199970, 299970), { delta: 100000, pct: (100000 / 299970) * 100 });
	assert.equal(baseDelta(100000, 100500), null);
	assert.equal(baseDelta(100000, null), null);
	assert.equal(baseDelta(100000, undefined), null);
});
