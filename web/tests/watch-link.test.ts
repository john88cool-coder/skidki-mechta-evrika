import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	OWNER_SETTING_KEY,
	PRICE_MAX,
	PRICE_MIN,
	START_LIMIT,
	WATCH_SHOPS,
	decodeWatchPayload,
	encodeWatchPayload,
	loadOwnerSetting,
	ownerWatchReady,
	parseTargetPrice,
	saveOwnerSetting,
	validBotUsername,
	watchCopyCommand,
	watchShopAllowed,
	watchStartLink,
	type OwnerBotSetting
} from '../src/lib/utils/watch-link.ts';

/** Общие Python↔TS векторы (бот: src/skidki/item_watch.py, tests/test_bot_watches_search.py). */
const VECTOR_SIMPLE = {
	shop: 'mechta',
	sku: 'A:17',
	maxPrice: 470000,
	payload: 'w2_WyJtZWNodGEiLCJBOjE3Iiw0NzAwMDBd'
} as const;
const VECTOR_UNICODE = {
	shop: 'mechta',
	sku: 'Е\u0301лка-\u{1F384}-9',
	maxPrice: 12990,
	payload: 'w2_WyJtZWNodGEiLCLQlcyB0LvQutCwLfCfjoQtOSIsMTI5OTBd'
} as const;
const VECTOR_MAX = {
	shop: 'mechta',
	sku: 'X'.repeat(25),
	maxPrice: 470000,
	payload: 'w2_WyJtZWNodGEiLCJYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYIiw0NzAwMDBd'
} as const;

/** Тестовый кодировщик произвольного JSON-массива: для векторов с невалидными значениями. */
function rawPayload(jsonText: string): string {
	const bytes = new TextEncoder().encode(jsonText);
	let bin = '';
	for (const b of bytes) bin += String.fromCharCode(b);
	return 'w2_' + btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Заглушка хранилища настроек. */
function fakeStorage(): {
	data: Map<string, string>;
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
} {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (key) => data.get(key) ?? null,
		setItem: (key, value) => void data.set(key, value)
	};
}

test('encode/decode: общий вектор mechta/A:17/470000 совпадает с ботом', () => {
	const payload = encodeWatchPayload(VECTOR_SIMPLE.shop, VECTOR_SIMPLE.sku, VECTOR_SIMPLE.maxPrice);
	assert.equal(payload, VECTOR_SIMPLE.payload);
	assert.deepEqual(decodeWatchPayload(VECTOR_SIMPLE.payload), {
		shop: 'mechta',
		sku: 'A:17',
		maxPrice: 470000
	});
});

test('encode/decode: Unicode-составной SKU (комбинируемое ударение + эмодзи) проходит', () => {
	const payload = encodeWatchPayload(VECTOR_UNICODE.shop, VECTOR_UNICODE.sku, VECTOR_UNICODE.maxPrice);
	assert.equal(payload, VECTOR_UNICODE.payload);
	assert.deepEqual(decodeWatchPayload(VECTOR_UNICODE.payload), {
		shop: 'mechta',
		sku: VECTOR_UNICODE.sku,
		maxPrice: 12990
	});
});

test('encode/decode: максимально длинный случай укладывается в лимит start 64', () => {
	const payload = encodeWatchPayload(VECTOR_MAX.shop, VECTOR_MAX.sku, VECTOR_MAX.maxPrice);
	assert.equal(payload, VECTOR_MAX.payload);
	assert.ok(payload!.length <= START_LIMIT);
	assert.deepEqual(decodeWatchPayload(payload!), {
		shop: 'mechta',
		sku: VECTOR_MAX.sku,
		maxPrice: 470000
	});
	// На символ длиннее payload перестаёт помещаться в /start, но команда ещё передаётся
	const over = encodeWatchPayload('mechta', 'X'.repeat(26), 470000);
	assert.ok(over);
	assert.equal(over!.length, START_LIMIT + 1);
	assert.equal(watchStartLink('john8_bot', over!), null);
	assert.ok(watchCopyCommand(over!).length <= 4096);
});

test('encode: строгий список магазинов, непустой SKU, цена 1..999999999', () => {
	assert.deepEqual([...WATCH_SHOPS], ['mechta', 'evrika', 'shopkz', 'sulpak', 'technodom', 'alser']);
	assert.equal(encodeWatchPayload('kaspi', '1', 100), null);
	assert.equal(encodeWatchPayload('', '1', 100), null);
	assert.equal(encodeWatchPayload('mechta', '', 100), null);
	assert.equal(encodeWatchPayload('mechta', '   ', 100), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', 0), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', -1), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', PRICE_MAX + 1), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', 47000.5), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', Number.NaN), null);
	assert.equal(encodeWatchPayload('mechta', 'A:17', Number.POSITIVE_INFINITY), null);
	assert.ok(encodeWatchPayload('mechta', 'A:17', PRICE_MIN));
	assert.ok(encodeWatchPayload('mechta', 'A:17', PRICE_MAX));
	assert.deepEqual(decodeWatchPayload(encodeWatchPayload('mechta', 'A:17', PRICE_MAX)!), {
		shop: 'mechta',
		sku: 'A:17',
		maxPrice: PRICE_MAX
	});
});

test('decode: алфавит base64url без padding, содержимое проверяется', () => {
	assert.equal(decodeWatchPayload('WyJtZWNodGEiLCJBOjE3Iiw0NzAwMDBd'), null); // без префикса
	assert.equal(decodeWatchPayload('w1_WyJtZWNodGE'), null); // чужой префикс
	assert.equal(decodeWatchPayload('w2_'), null); // пустое тело
	assert.equal(decodeWatchPayload('w2_WyJtZWNodGE='), null); // padding запрещён
	assert.equal(decodeWatchPayload('w2_WyJtZWNodG+/'), null); // не base64url-алфавит
	assert.equal(decodeWatchPayload('w2_%%%'), null);
	assert.equal(decodeWatchPayload('w2__w'), null); // невалидный UTF-8
	assert.equal(decodeWatchPayload(rawPayload('{"shop":"mechta"}')), null); // не массив
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17"]')), null); // не 3 элемента
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17",1,"x"]')), null);
	assert.equal(decodeWatchPayload(rawPayload('["kaspi","1",5]')), null); // магазин не в списке
	assert.equal(decodeWatchPayload(rawPayload('["Mechta","A:17",5]')), null); // регистр важен
	assert.equal(decodeWatchPayload(rawPayload('["mechta","",5]')), null); // пустой SKU
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17",0]')), null); // цена 0
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17",1000000000]')), null);
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17",1.5]')), null); // не целое
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17",true]')), null); // bool не цена
	assert.equal(decodeWatchPayload(rawPayload('["mechta","A:17","470000"]')), null);
	assert.equal(decodeWatchPayload(rawPayload('[1,"A:17",5]')), null);
});

test('link: только https://t.me/, username валидируется, payload ≤ 64', () => {
	const payload = VECTOR_SIMPLE.payload;
	const link = watchStartLink('john8_bot', payload);
	assert.equal(link, 'https://t.me/john8_bot?start=' + payload);
	assert.ok(link!.startsWith('https://t.me/'));
	assert.equal(watchStartLink('john-bot', payload), null); // дефис
	assert.equal(watchStartLink('1john_bot', payload), null); // начинается с цифры
	assert.equal(watchStartLink('_john_bot', payload), null);
	assert.equal(watchStartLink('john8_user', payload), null); // не бот
	assert.equal(watchStartLink('bbot', payload), null); // короче 5
	assert.equal(watchStartLink('a'.repeat(29) + '_bot', payload), null); // длиннее 32
	assert.equal(watchStartLink('', payload), null);
	assert.equal(watchStartLink('джон8_bot', payload), null);
	assert.equal(watchStartLink('john8_bot', 'x' + payload.slice(1)), null); // не w2_
	assert.equal(watchStartLink('john8_bot', VECTOR_MAX.payload + 'ab'), null); // длиннее 64
	// ровно 64 символа — лимит соблюдён, ссылка строится
	assert.ok(watchStartLink('john8_bot', 'w2_' + 'a'.repeat(61)));
});

test('username: 5–32 символа, буквы/цифры/подчёркивание, суффикс bot', () => {
	assert.equal(validBotUsername('john8_bot'), true);
	assert.equal(validBotUsername('ShopWatch_Bot'), true);
	assert.equal(validBotUsername('A_bot'), true);
	assert.equal(validBotUsername(''), false);
	assert.equal(validBotUsername('ab'), false);
	assert.equal(validBotUsername('john-bot'), false);
	assert.equal(validBotUsername('john8_user'), false);
	assert.equal(validBotUsername('1john_bot'), false);
	assert.equal(validBotUsername('_john_bot'), false);
	assert.equal(validBotUsername('джон8_bot'), false);
	assert.equal(validBotUsername('a'.repeat(29) + '_bot'), false);
});

test('parseTargetPrice: целое ₸ от 1 до 999999999', () => {
	assert.equal(parseTargetPrice('470000'), 470000);
	assert.equal(parseTargetPrice(' 4500 '), 4500);
	assert.equal(parseTargetPrice('1'), PRICE_MIN);
	assert.equal(parseTargetPrice('999999999'), PRICE_MAX);
	assert.equal(parseTargetPrice('0'), null);
	assert.equal(parseTargetPrice('-5'), null);
	assert.equal(parseTargetPrice('12.5'), null);
	assert.equal(parseTargetPrice('12,5'), null);
	assert.equal(parseTargetPrice('1000000000'), null);
	assert.equal(parseTargetPrice('abc'), null);
	assert.equal(parseTargetPrice(''), null);
	assert.equal(parseTargetPrice('470 000'), null); // без разделителей разрядов
});

test('encode: команда /watchitem укладывается в лимит сообщения Telegram', () => {
	const ok = encodeWatchPayload('mechta', 'X'.repeat(3041), 470000);
	assert.ok(ok);
	assert.ok(watchCopyCommand(ok!).length <= 4096);
	assert.equal(encodeWatchPayload('mechta', 'X'.repeat(3042), 470000), null);
	assert.equal(encodeWatchPayload('mechta', 'X'.repeat(5000), 470000), null);
});

test('payload не содержит title, chat ID или токен — только магазин, SKU и цена', () => {
	const payload = encodeWatchPayload('mechta', 'A:17', 470000)!;
	const link = watchStartLink('john8_bot', payload)!;
	assert.ok(!link.includes('iPhone')); // title не входит
	assert.ok(!link.includes('366256716')); // chat ID
	assert.ok(!/:\d{20,}/.test(link)); // токен бота
	const decoded = decodeWatchPayload(payload)!;
	assert.deepEqual(decoded, { shop: 'mechta', sku: 'A:17', maxPrice: 470000 });
	assert.equal(Object.keys(decoded).length, 3); // ровно три поля, ничего лишнего
	assert.equal(watchCopyCommand(payload), '/watchitem ' + payload);
});

test('watchShopAllowed: только магазины со включённым каталогом', () => {
	assert.equal(watchShopAllowed('mechta'), true);
	assert.equal(watchShopAllowed('alser'), true);
	assert.equal(watchShopAllowed('kaspi'), false);
	assert.equal(watchShopAllowed(''), false);
});

test('настройка владельца: по умолчанию выключена, кривые данные игнорируются', () => {
	assert.deepEqual(loadOwnerSetting(null), { username: '', enabled: false });
	const store = fakeStorage();
	assert.deepEqual(loadOwnerSetting(store), { username: '', enabled: false });
	store.setItem(OWNER_SETTING_KEY, '{oops');
	assert.deepEqual(loadOwnerSetting(store), { username: '', enabled: false });
	store.setItem(OWNER_SETTING_KEY, 'null');
	assert.deepEqual(loadOwnerSetting(store), { username: '', enabled: false });
	store.setItem(OWNER_SETTING_KEY, '[]');
	assert.deepEqual(loadOwnerSetting(store), { username: '', enabled: false });
	store.setItem(OWNER_SETTING_KEY, JSON.stringify({ username: 42, enabled: true }));
	assert.deepEqual(loadOwnerSetting(store), { username: '', enabled: false });
	const setting: OwnerBotSetting = { username: 'john8_bot', enabled: true };
	saveOwnerSetting(store, setting);
	assert.deepEqual(loadOwnerSetting(store), setting);
	assert.equal(ownerWatchReady(setting), true);
	assert.equal(ownerWatchReady({ username: 'john8_bot', enabled: false }), false);
	assert.equal(ownerWatchReady({ username: 'john-bot', enabled: true }), false);
});
