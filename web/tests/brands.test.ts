import { test } from 'node:test';
import assert from 'node:assert/strict';
import { brandKey, brandOptions } from '../src/lib/utils/brands.ts';

const deal = (brand: string | null, sku: string) => ({
	product: { shop: 's', sku, title: 't', price: 1, url: '#', in_stock: true, brand }
});

test('brand duplicates by case and spaces are merged', () => {
	assert.equal(brandKey(' BORK '), 'bork');
	assert.equal(brandKey(null), '');
	const options = brandOptions([
		deal('BORK', '1'), deal('Bork', '2'), deal('BORK', '3'),
		deal('Oscal', '4'), deal('Oscal ', '5'), deal(null, '6'), deal('  ', '7')
	]);
	assert.deepEqual(options, [
		{ key: 'bork', label: 'BORK', count: 3 },
		{ key: 'oscal', label: 'Oscal', count: 2 }
	]);
});
