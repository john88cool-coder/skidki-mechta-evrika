import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeSnapshots } from '../src/lib/utils/merge.ts';

const shop = (name: string, last_crawl: string | null, item_count = 10) => ({
	name, label: name, last_crawl, item_count, status: last_crawl ? 'ok' as const : 'error' as const
});
const deal = (shopName: string, sku: string, drop_pct: number, badges: string[] = []) => ({
	product: { shop: shopName, sku, title: sku, price: 100, url: '#', in_stock: true },
	signal: 'deal' as const, drop_pct, badges
});

const cloud = {
	updated_at: '2026-09-23T00:00:00+00:00',
	deals: [deal('evrika', 'e1', 40), deal('mechta', 'stale', 90)],
	shops: [shop('mechta', null, 0), shop('evrika', '2026-09-23T00:00:00+00:00', 3772)],
	stats: { total_products: 3772, total_deals: 2, avg_discount: 65 }
};
const local = {
	updated_at: '2026-09-23T01:00:00+00:00',
	deals: [deal('mechta', 'm1', 60), deal('mechta', 'fake', 80, ['Рисованная?']), deal('evrika', 'old', 99)],
	shops: [shop('mechta', '2026-09-23T01:00:00+00:00', 7717), shop('evrika', null, 0)],
	stats: { total_products: 7717, total_deals: 3, avg_discount: 60 }
};

test('local snapshot replaces only the shops the PC actually crawled', () => {
	const merged = mergeSnapshots(cloud, local)!;
	assert.deepEqual(merged.shops.map((s) => [s.name, s.item_count]), [['mechta', 7717], ['evrika', 3772]]);
	// evrika — из облака, mechta — из ПК; «old» evrika из локального среза отброшен.
	assert.deepEqual(merged.deals.map((d) => d.product.sku), ['m1', 'e1', 'fake']);
	assert.equal(merged.stats.total_products, 7717 + 3772);
	assert.equal(merged.updated_at, local.updated_at);
});

test('missing snapshots degrade gracefully', () => {
	assert.equal(mergeSnapshots(cloud, null), cloud);
	assert.equal(mergeSnapshots(null, local), local);
	assert.equal(mergeSnapshots(null, null), null);
});
