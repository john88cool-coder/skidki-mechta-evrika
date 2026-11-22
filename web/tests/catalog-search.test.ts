import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchCatalog, mapLimit, gatherRows, createOnceGate } from '../src/lib/utils/catalog-search.ts';
import type { CatalogRow, CatalogIndex } from '../src/lib/types.ts';
import type { CatalogLoader, ShopSourceBinding } from '../src/lib/utils/catalog-source.ts';

const row = (over: Partial<CatalogRow['product']> & { sku: string; title: string; url: string; price: number }, extra: Partial<CatalogRow> = {}): CatalogRow => ({
	product: { shop: 'mechta', in_stock: true, ...over } as CatalogRow['product'],
	last_seen: null,
	base_price: null,
	fair_discount: null,
	pump_price: null,
	exact_model: null,
	...extra
});

const ROWS: CatalogRow[] = [
	// Прямое совпадение модели (mechta) и та же модель в другой сети (shopkz).
	row({ shop: 'mechta', sku: 'A:17', title: 'Demo Phone 256', url: 'https://mechta.kz/item/demo-phone-256/', price: 100000, mpn: 'DP256' }),
	row({ shop: 'shopkz', sku: 'A:17', title: 'Demo Phone 256', url: 'https://shopkz.kz/p/demo-phone-256', price: 95000, mpn: 'DP256' }),
	// Младшая модель.
	row({ shop: 'mechta', sku: 'C:3', title: 'Demo Phone 128', url: 'https://mechta.kz/item/demo-phone-128/', price: 80000 }),
	// Аксессуар: все слова запроса есть в названии, но это не сама модель.
	row({ shop: 'mechta', sku: 'B:2', title: 'Чехол для Demo Phone 256', url: 'https://mechta.kz/item/case-demo-256/', price: 5000 }),
	// Два разных магазинных URL с разными значимыми query-параметрами.
	row({ shop: 'mechta', sku: 'D:4', title: 'Demo Phone 256 Black', url: 'https://mechta.kz/item/demo-phone-256/?color=black', price: 100000 }),
	row({ shop: 'mechta', sku: 'E:5', title: 'Demo Phone 256 White', url: 'https://mechta.kz/item/demo-phone-256/?color=white', price: 100000 }),
	// Равная релевантность, разная доступность и цена — для проверки последних ключей сортировки.
	row({ shop: 'mechta', sku: 'F:6', title: 'Demo Phone 256', url: 'https://mechta.kz/item/demo-phone-256-f/', price: 1000, in_stock: false }),
	row({ shop: 'shopkz', sku: 'G:7', title: 'Demo Phone 256', url: 'https://shopkz.kz/p/demo-phone-256-g', price: 3000 }),
	row({ shop: 'shopkz', sku: 'H:8', title: 'Demo Phone 256', url: 'https://shopkz.kz/p/demo-phone-256-h', price: 2000 }),
	// Ё для проверки нормализации.
	row({ shop: 'mechta', sku: 'I:9', title: 'Ёлка гирлянда', url: 'https://mechta.kz/item/yolka/', price: 1500 })
];

const skus = (rows: CatalogRow[]) => rows.map((r) => r.product.sku);

test('пустая строка и пробелы возвращают пустой массив', () => {
	assert.deepEqual(searchCatalog(ROWS, '', 10), []);
	assert.deepEqual(searchCatalog(ROWS, '   ', 10), []);
});

test('«demo 256» находит обе сети', () => {
	const found = searchCatalog(ROWS, 'demo 256', 10);
	assert.ok(found.some((r) => r.product.shop === 'mechta'));
	assert.ok(found.some((r) => r.product.shop === 'shopkz'));
});

test('«DEMO   128» находит младшую модель', () => {
	const found = searchCatalog(ROWS, 'DEMO   128', 10);
	assert.deepEqual(skus(found), ['C:3']);
});

test('точный SKU сохраняет двоеточие', () => {
	const found = searchCatalog(ROWS, 'A:17', 10);
	assert.deepEqual(skus(found), ['A:17', 'A:17']);
});

test('подстрока SKU не считается точным совпадением', () => {
	// «a:1» — не точный SKU и не слово из названия/бренда/MPN.
	assert.deepEqual(searchCatalog(ROWS, 'a:1', 10), []);
});

test('прямое совпадение модели опережает аксессуар', () => {
	const found = searchCatalog(ROWS, 'demo 256', 10);
	assert.equal(found[found.length - 1].product.sku, 'B:2');
	assert.notEqual(found[0].product.sku, 'B:2');
});

test('ссылка с utm_source=x находит позицию (fragment и завершающий слэш не мешают)', () => {
	const found = searchCatalog(ROWS, 'https://mechta.kz/item/demo-phone-128/?utm_source=x#reviews', 10);
	assert.deepEqual(skus(found), ['C:3']);
	// Тот же товар без utm, без fragment и без завершающего слэша.
	const again = searchCatalog(ROWS, 'https://mechta.kz/item/demo-phone-128', 10);
	assert.deepEqual(skus(again), ['C:3']);
});

test('чужой hostname с тем же path возвращает пусто', () => {
	assert.deepEqual(searchCatalog(ROWS, 'https://evil.kz/item/demo-phone-128/', 10), []);
});

test('два разных магазинных URL с разными значимыми query сохраняются', () => {
	const black = searchCatalog(ROWS, 'https://mechta.kz/item/demo-phone-256/?color=black', 10);
	assert.deepEqual(skus(black), ['D:4']);
	const white = searchCatalog(ROWS, 'https://mechta.kz/item/demo-phone-256/?color=white', 10);
	assert.deepEqual(skus(white), ['E:5']);
});

test('произвольная строка с двоеточием не трактуется как ссылка и не ходит в сеть', () => {
	assert.deepEqual(searchCatalog(ROWS, 'посмотри на https://example.com/x прямо', 10), []);
});

test('нормализация: NFKC, нижний регистр, ё → е, схлопывание пробелов', () => {
	assert.deepEqual(searchCatalog(ROWS, '  ёЛКА\t гирлянда ', 10).map((r) => r.product.sku), ['I:9']);
});

test('доступным позициям преимущество при равной релевантности', () => {
	// F:6 дешевле и то же название, но недоступен — G:7/H:8 впереди него.
	const found = searchCatalog(ROWS, 'demo 256', 10);
	const order = skus(found);
	assert.ok(order.indexOf('G:7') < order.indexOf('F:6'));
	assert.ok(order.indexOf('H:8') < order.indexOf('F:6'));
});

test('последние ключи сортировки — цена, магазин, SKU', () => {
	// G:7 и H:8 одинаково релевантны и доступны → дешевле впереди.
	const found = searchCatalog(ROWS, 'demo 256', 10);
	const order = skus(found);
	assert.ok(order.indexOf('H:8') < order.indexOf('G:7'));
});

test('limit соблюдается', () => {
	assert.equal(searchCatalog(ROWS, 'demo', 3).length, 3);
	assert.equal(searchCatalog(ROWS, 'demo', 0).length, 0);
});

test('mapLimit держит не больше limit одновременных задач', async () => {
	let active = 0;
	let peak = 0;
	const items = Array.from({ length: 10 }, (_, i) => i);
	await mapLimit(items, 3, async (n) => {
		active += 1;
		peak = Math.max(peak, active);
		await new Promise((r) => setTimeout(r, 5));
		active -= 1;
		assert.ok(active <= 3, `активных ${active} > 3`);
	});
	assert.equal(peak, 3);
});

test('mapLimit сохраняет порядок результатов', async () => {
	const out = await mapLimit([1, 2, 3, 4], 3, async (n) => {
		await new Promise((r) => setTimeout(r, (5 - n) * 5));
		return n * 10;
	});
	assert.deepEqual(out, [10, 20, 30, 40]);
});

const binding = (entry: ShopSourceBinding['entry']): ShopSourceBinding => ({
	side: 'cloud',
	last_crawl: '2026-11-21T12:00:00Z',
	entry,
	mismatch: false
});

const INDEX: CatalogIndex = {
	schema: 2,
	shop: 'mechta',
	rows: [row({ shop: 'mechta', sku: 'A:17', title: 'Demo Phone 256', url: 'https://mechta.kz/item/demo-phone-256/', price: 100000 })]
};

function fakeLoader(shops: Record<string, ShopSourceBinding>, indexes: Record<string, CatalogIndex | Error>): CatalogLoader {
	return {
		refreshSources: async () => new Map(Object.entries(shops)),
		getSource: async (shop) => shops[shop] ?? null,
		loadIndex: async (shop) => {
			const v = indexes[shop];
			if (v instanceof Error) throw v;
			return v ?? null;
		},
		loadHistory: async () => null
	};
}

test('gatherRows: собирает строки, отмечает витринные и недоступные магазины', async () => {
	const entry = {
		last_crawl: '2026-11-21T12:00:00Z',
		count: 1,
		index_sha256: 'x',
		history_sha256: 'y'
	};
	const loader = fakeLoader(
		{
			mechta: binding(entry),
			evrika: binding(null), // только Stage 1
			technodom: binding(entry)
		},
		{ mechta: INDEX, technodom: new Error('HTTP 500') }
	);
	const partials: number[] = [];
	const res = await gatherRows(loader, {
		concurrency: 3,
		onPartial: (p) => partials.push(p.rows.length)
	});
	assert.deepEqual(res.rows.map((r) => r.product.sku), ['A:17']);
	assert.deepEqual(res.ok, ['mechta']);
	assert.deepEqual(res.showcaseOnly, ['evrika']);
	assert.deepEqual(res.failed, ['technodom']);
	// Промежуточные обновления приходили по мере готовности индексов.
	assert.ok(partials.includes(1));
});

test('mapLimit: сборка не падает на пустом списке магазинов', async () => {
	const loader = fakeLoader({}, {});
	const res = await gatherRows(loader, {});
	assert.deepEqual(res.rows, []);
	assert.deepEqual(res.ok, []);
});

test('onceGate: повторный вызов во время загрузки не создаёт новое поколение и не гасит загрузку', async () => {
	// Регрессия Critical: инкремент поколения при каждом keystroke отключал
	// полный каталог палитры — результат первой загрузки отбрасывался.
	let calls = 0;
	let loading = false;
	let release!: () => void;
	const gate = createOnceGate(async () => {
		calls += 1;
		loading = true;
		await new Promise<void>((r) => (release = r));
		loading = false;
		return 'done';
	});
	const first = gate();
	const second = gate(); // повторный вызов, пока первая загрузка идёт
	assert.equal(calls, 1, 'start должен быть вызван один раз');
	assert.equal(loading, true, 'повторный вызов не гасит состояние загрузки');
	release();
	assert.equal(await first, 'done');
	assert.equal(await second, 'done', 'результат первой загрузки доезжает до всех вызовов');
	assert.equal(loading, false);
	// Успех мемоизируется — новых запусков нет.
	assert.equal(await gate(), 'done');
	assert.equal(calls, 1);
});

test('onceGate: сбой сбрасывает врата — следующий вызов повторяет попытку', async () => {
	let calls = 0;
	const gate = createOnceGate(async () => {
		calls += 1;
		if (calls === 1) throw new Error('HTTP 500');
		return 'ok';
	});
	await assert.rejects(gate(), /HTTP 500/);
	assert.equal(await gate(), 'ok');
	assert.equal(calls, 2);
});
