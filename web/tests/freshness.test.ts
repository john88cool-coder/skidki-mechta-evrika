import { test } from 'node:test';
import assert from 'node:assert/strict';
import { freshnessOf } from '../src/lib/utils/merge.ts';

const shop = (name: string, last_crawl: string | null) => ({
	name, label: name, last_crawl, item_count: 1, status: 'ok' as const
});

test('freshness reports the oldest shop crawl, not the newest', () => {
	const now = Date.parse('2026-11-15T16:00:00Z');
	const f = freshnessOf(
		[shop('mechta', '2026-11-15T15:21:00Z'), shop('sulpak', '2026-11-15T09:50:00Z'), shop('dns', null)],
		now
	);
	assert.equal(f.oldest, '2026-11-15T09:50:00Z');
	assert.equal(f.newest, '2026-11-15T15:21:00Z');
	assert.equal(f.stale, true);
	assert.equal(freshnessOf([shop('mechta', '2026-11-15T15:21:00Z')], now).stale, false);
	assert.deepEqual(freshnessOf([], now), { oldest: null, newest: null, stale: true });
});
