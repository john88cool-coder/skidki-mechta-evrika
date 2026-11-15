import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getSnapshot, rememberProduct, resolveDealsWithSnapshots } from '../src/lib/utils/snapshots.ts';

function memoryStorage() {
	const map = new Map<string, string>();
	return {
		getItem: (k: string) => map.get(k) ?? null,
		setItem: (k: string, v: string) => {
			map.set(k, v);
		}
	};
}

test('snapshots keep favorite/compared items visible even after leaving top-300 deals', () => {
	const store = memoryStorage();
	const savedProduct = {
		shop: 'shopkz',
		sku: 'A/B+1',
		title: 'Ноутбук ASUS Zenbook 14',
		price: 449_990,
		old_price: 549_990,
		url: 'https://shop.kz/offer/zenbook-14/',
		brand: 'ASUS',
		in_stock: true,
		image: 'https://cdn/zen.jpg',
		rating: 4.8,
		reviews_count: 64
	};
	rememberProduct(savedProduct, store);
	assert.equal(getSnapshot('shopkz:A/B+1', store)?.title, 'Ноутбук ASUS Zenbook 14');

	// В текущем срезе осталась только другая позиция (mechta:2):
	const activeDeals = [
		{
			product: { shop: 'mechta', sku: '2', title: 'Смартфон', price: 199_990, url: 'https://mechta.kz/2', in_stock: true },
			signal: 'deal' as const,
			drop_pct: 25,
			badges: []
		}
	];
	const resolved = resolveDealsWithSnapshots(['shopkz:A/B+1', 'mechta:2'], activeDeals, store);
	assert.equal(resolved.deals.length, 2);
	assert.equal(resolved.deals[0].product.title, 'Ноутбук ASUS Zenbook 14');
	assert.equal(resolved.deals[0].product.url, 'https://shop.kz/offer/zenbook-14/');
	assert.equal(resolved.archivedIds.has('shopkz:A/B+1'), true);
	assert.equal(resolved.archivedIds.has('mechta:2'), false);
});
