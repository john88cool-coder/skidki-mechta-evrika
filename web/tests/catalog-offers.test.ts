import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	offersFor,
	offersVisibleFor,
	partialOffers,
	type OfferRow
} from '../src/lib/utils/catalog-offers.ts';
import type { CatalogIndex, CatalogRow, Product } from '../src/lib/types.ts';
/** Товар в строке индекса: цена, наличие и комплектация настраиваются. */
const product = (over: Partial<Product> = {}): Product => ({
	shop: 'mechta',
	sku: 'A:17',
	title: 'Demo Phone 256 GB',
	price: 120000,
	url: 'https://www.mechta.kz/product/demo-a17/',
	brand: 'Demo',
	in_stock: true,
	...over
});

const row = (over: Partial<OfferRow> = {}): OfferRow => ({
	product: product(),
	last_seen: '2026-11-21T12:00:00Z',
	base_price: null,
	fair_discount: null,
	pump_price: null,
	exact_model: 'demo:DP256-KZ',
	...over
} as OfferRow);

/** Вариант строки с другим магазином/SKU/ценой/наличием/комплектацией. */
const offer = (over: Partial<Product> & { exact_model?: string | null; last_seen?: string | null } = {}): OfferRow => {
	const { exact_model, last_seen, ...p } = over;
	return row({ product: product(p), exact_model: exact_model ?? 'demo:DP256-KZ', last_seen });
};

/** Индекс магазина из строк-офферов: точный тип поля в CatalogRow ещё null,
 * реальный экспорт после задачи 6 пишет ключи — каст локален тесту. */
const index = (shop: string, rows: OfferRow[]): CatalogIndex =>
	({ schema: 2, shop, rows }) as unknown as CatalogIndex;

/** Контроль fixture (задача 6): mechta/A:17 ищет офферы в shopkz и alser. */
const TARGET = row();
const FIXTURE_ROWS: OfferRow[] = [
	offer({ shop: 'shopkz', sku: '77', price: 115000, url: 'https://shop.kz/offer/77/' }),
	offer({ shop: 'alser', sku: '78', price: 95000, title: 'Demo Phone 128 GB', exact_model: 'demo:DP128-KZ' }),
	row({ product: product({ sku: 'CASE01', title: 'Чехол Demo Phone', brand: null, price: 4990 }), exact_model: null }),
	// Тот же магазин, что у цели — не «другой магазин», а дубликат identity.
	offer({ shop: 'mechta', sku: 'A:17', price: 119000 })
];

const FIXTURE_INDEXES = new Map([
	['mechta', index('mechta', FIXTURE_ROWS.filter((r) => r.product.shop === 'mechta'))],
	['shopkz', index('shopkz', FIXTURE_ROWS.filter((r) => r.product.shop === 'shopkz'))],
	['alser', index('alser', FIXTURE_ROWS.filter((r) => r.product.shop === 'alser'))]
]);

test('offersFor: контроль fixture — shopkz/77 дешевле на 5000 ₸; alser/78 и чехол исключены', () => {
	const offers = offersFor(TARGET, FIXTURE_INDEXES);
	assert.ok(offers, 'у цели с ключом список не null');
	assert.equal(offers.length, 1);
	assert.equal(offers[0].product.shop, 'shopkz');
	assert.equal(offers[0].product.sku, '77');
	assert.equal(offers[0].product.price, 115000);
	assert.equal(TARGET.product.price - offers[0].product.price, 5000);
});

test('offersFor: только та же exact_model и актуальное наличие', () => {
	const rows: OfferRow[] = [
		offer({ shop: 'shopkz', sku: '77', price: 115000 }),
		// Другая комплектация и товар без ключа не совпадают:
		offer({ shop: 'alser', sku: '78', price: 95000, exact_model: 'demo:DP128-KZ' }),
		row({ product: product({ shop: 'sulpak', sku: '9', title: 'Чехол' }), exact_model: null }),
		// Снятое с продажи предложение — не «актуальное доступное»:
		offer({ shop: 'technodom', sku: 'td9', price: 90000, in_stock: false })
	];
	const indexes = new Map([['other', index('other', rows)]]);
	const offers = offersFor(TARGET, indexes);
	assert.ok(offers, 'у цели с ключом список не null');
	assert.deepEqual(offers.map((o) => o.product.sku), ['77']);
});

test('offersFor: identity цели исключён, включая строку из чужого индекса', () => {
	const rows: OfferRow[] = [
		offer({ shop: 'shopkz', sku: '77', price: 115000 }),
		offer({ shop: 'mechta', sku: 'A:17', price: 100000 })
	];
	const indexes = new Map([['x', index('x', rows)]]);
	const offers = offersFor(TARGET, indexes);
	assert.ok(offers, 'у цели с ключом список не null');
	assert.equal(offers.length, 1);
	assert.equal(offers[0].product.shop, 'shopkz');
});

test('offersFor: по магазину остаётся самая низкая доступная цена', () => {
	const rows: OfferRow[] = [
		offer({ shop: 'shopkz', sku: '77', price: 118000 }),
		offer({ shop: 'shopkz', sku: '78', price: 112000 }),
		offer({ shop: 'alser', sku: '5', price: 105000 }),
		// Недоступная цена ниже доступной не участвует в минимуме:
		offer({ shop: 'shopkz', sku: '79', price: 100000, in_stock: false })
	];
	const indexes = new Map([['x', index('x', rows)]]);
	const offers = offersFor(TARGET, indexes);
	assert.ok(offers, 'у цели с ключом список не null');
	assert.deepEqual(
		offers.map((o) => [o.product.shop, o.product.sku, o.product.price]),
		[
			['alser', '5', 105000],
			['shopkz', '78', 112000]
		]
	);
});

test('offersFor: сортировка цена → магазин → SKU (одна строка на магазин)', () => {
	const rows: OfferRow[] = [
		offer({ shop: 'sulpak', sku: 'b', price: 110000 }),
		offer({ shop: 'alser', sku: 'a', price: 110000 }),
		offer({ shop: 'technodom', sku: 'c', price: 110000 }),
		offer({ shop: 'shopkz', sku: 'z', price: 100000 }),
		// Дубликат в том же магазине дешевле не делает: остаётся минимум 112000
		// из предыдущего сценария — здесь проверяем равные цены разных магазинов.
		offer({ shop: 'evrika', sku: 'a', price: 110000 })
	];
	const indexes = new Map([['x', index('x', rows)]]);
	const offers = offersFor(TARGET, indexes);
	assert.ok(offers, 'у цели с ключом список не null');
	assert.deepEqual(
		offers.map((o) => `${o.product.shop}:${o.product.sku}`),
		['shopkz:z', 'alser:a', 'evrika:a', 'sulpak:b', 'technodom:c']
	);
});

test('offersFor: без подтверждённого артикула у цели блок скрыт (null)', () => {
	const noKey = row({ exact_model: null });
	assert.equal(offersFor(noKey, FIXTURE_INDEXES), null);
});

test('partialOffers: при неполных данных — пометка «среди загруженных предложений»', () => {
	// Загружен только один индекс из трёх магазинов каталога — данные неполные.
	const partial = new Map([['shopkz', FIXTURE_INDEXES.get('shopkz')!]]);
	const state = partialOffers(TARGET, partial, ['mechta', 'shopkz', 'alser']);
	if (!state) assert.fail('ожидается состояние офферов');
	assert.equal(state.partial, true);
	assert.equal(state.note, 'среди загруженных предложений');
	assert.equal(state.offers.length, 1);
	// Все индексы загружены — формулировка не нужна.
	const full = partialOffers(TARGET, FIXTURE_INDEXES, ['mechta', 'shopkz', 'alser']);
	if (!full) assert.fail('ожидается состояние офферов');
	assert.equal(full.partial, false);
	assert.equal(full.note, null);
});

test('partialOffers: цель без ключа — блок скрыт даже при неполных данных', () => {
	const noKey = row({ exact_model: null });
	const partial = new Map([['shopkz', FIXTURE_INDEXES.get('shopkz')!]]);
	assert.equal(partialOffers(noKey, partial, ['mechta', 'shopkz', 'alser']), null);
});

test('offersVisibleFor: сбой первого нажатия виден без собранного state — с «Повторить»', () => {
	// Сбой до установки state: блок видим, потому что есть ошибка (иначе ревью-дефект —
	// пользователю нечего нажать). Ссылка на товар совпадает с владельцем запроса.
	assert.equal(
		offersVisibleFor('mechta:A:17', { ownerIdentity: 'mechta:A:17', state: null, error: 'HTTP 503' }),
		true
	);
	// Успешная сборка (state есть, ошибки нет) — блок виден.
	assert.equal(
		offersVisibleFor('mechta:A:17', {
			ownerIdentity: 'mechta:A:17',
			state: { kind: 'ready' },
			error: null
		}),
		true
	);
	// Пустой результат и «нет ключа» — блок виден/скрыт как раньше.
	assert.equal(
		offersVisibleFor('mechta:A:17', { ownerIdentity: 'mechta:A:17', state: { kind: 'empty' }, error: null }),
		true
	);
	assert.equal(
		offersVisibleFor('mechta:A:17', { ownerIdentity: 'mechta:A:17', state: { kind: 'hidden' }, error: null }),
		false
	);
});

test('offersVisibleFor: ответ чужого запроса не рендерится на другом товаре (A → B)', () => {
	// Офферы собраны для A, пользователь уже на B — блок скрыт даже с ошибкой A.
	assert.equal(
		offersVisibleFor('shopkz:77', { ownerIdentity: 'mechta:A:17', state: { kind: 'ready' }, error: null }),
		false
	);
	assert.equal(
		offersVisibleFor('shopkz:77', { ownerIdentity: 'mechta:A:17', state: null, error: 'HTTP 503' }),
		false
	);
	// Без карточки блока нет вовсе.
	assert.equal(
		offersVisibleFor(null, { ownerIdentity: 'mechta:A:17', state: { kind: 'ready' }, error: null }),
		false
	);
});
