import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeSnapshots } from '../src/lib/utils/merge.ts';
import { groupLabel } from '../src/lib/utils/format.ts';

test('groupLabel translates "other" to Russian label instead of raw slug', () => {
	assert.equal(groupLabel('other'), '🗂 Прочее');
	assert.equal(groupLabel('phones'), '📱 Смартфоны');
});

test('mergeSnapshots ranks real drops with null drop_pct and computes honest avg_discount', () => {
	const cloud = {
		updated_at: '2026-11-12T10:00:00Z',
		deals: [
			{
				product: { shop: 'evrika', sku: 'e-deal', title: 'Наушники', price: 80_000, url: '#', in_stock: true },
				signal: 'deal' as const,
				drop_pct: 20,
				fair_discount: 10,
				value_score: 55,
				badges: []
			}
		],
		shops: [{ name: 'evrika', label: 'Эврика', last_crawl: '2026-11-12T10:00:00Z', item_count: 3000, status: 'ok' as const }],
		stats: { total_products: 3000, total_deals: 1, avg_discount: 20 }
	};
	const local = {
		updated_at: '2026-11-12T10:30:00Z',
		deals: [
			{
				product: { shop: 'mechta', sku: 'm-drop', title: 'Ноутбук', price: 280_000, url: '#', in_stock: true },
				signal: 'drop' as const,
				drop_pct: null,
				fair_discount: 35,
				value_score: 82,
				badges: ['Выбор ИС', 'Честная скидка']
			}
		],
		shops: [{ name: 'mechta', label: 'Мечта', last_crawl: '2026-11-12T10:30:00Z', item_count: 7500, status: 'ok' as const }],
		stats: { total_products: 7500, total_deals: 1, avg_discount: 35 }
	};

	const merged = mergeSnapshots(cloud, local)!;
	// Реальное снижение цены без старого ценника (value_score=82, fair_discount=35) должно быть первым, а не падать в 0!
	assert.deepEqual(merged.deals.map((d) => d.product.sku), ['m-drop', 'e-deal']);
	// Медиана эффективных скидок [10, 35] -> 35 (а не [0, 20] -> 20)
	assert.equal(merged.stats.avg_discount, 35);
});
