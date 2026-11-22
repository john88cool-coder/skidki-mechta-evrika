import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SideVersions } from '../src/lib/utils/history.ts';

/** Мини-срез: важен только признак версии содержимого. */
interface Slice {
	updated_at: string;
	price: number;
}

const slice = (updated_at: string, price: number): Slice => ({ updated_at, price });

/** Счётчик обращений к «файлу истории» стороны. */
function counting(files: Record<string, Slice | null>) {
	const calls: string[] = [];
	return {
		calls,
		fetch: async (version: string): Promise<Slice | null> => {
			calls.push(version);
			return files[version] ?? null;
		}
	};
}

test('регрессия: смена версии стороны перезагружает срез, повторная та же версия — нет', async () => {
	const sides = new SideVersions<Slice>();
	const files = { v1: slice('2026-11-21T10:00:00Z', 120000), v2: slice('2026-11-21T12:00:00Z', 115000) };
	const c = counting(files);

	await sides.load('cloud', 'v1', () => c.fetch('v1'));
	assert.equal(c.calls.length, 1);
	assert.equal(sides.get('cloud')?.price, 120000);

	// та же версия — файл уже загружен, повторного обращения нет
	await sides.load('cloud', 'v1', () => c.fetch('v1'));
	assert.equal(c.calls.length, 1);

	// новая публикация (новый latest): сторона обязана перезагрузиться
	await sides.load('cloud', 'v2', () => c.fetch('v2'));
	assert.equal(c.calls.length, 2);
	assert.equal(sides.get('cloud')?.price, 115000);
});

test('неудачная загрузка не фиксирует версию: повтор при той же версии повторяет запрос', async () => {
	const sides = new SideVersions<Slice>();
	let fail = true;
	let calls = 0;
	const fetch = async (): Promise<Slice | null> => {
		calls += 1;
		if (fail) throw new Error('HTTP 500');
		return slice('2026-11-21T12:00:00Z', 115000);
	};

	await assert.rejects(sides.load('cloud', 'v2', fetch), /HTTP 500/);
	assert.equal(sides.get('cloud'), null);
	assert.equal(sides.hasAny(), false);

	fail = false;
	await sides.load('cloud', 'v2', fetch);
	assert.equal(calls, 2);
	assert.equal(sides.get('cloud')?.price, 115000);
});

test('404 — валидная пустая версия: та же версия не пере запрашивается, новая — запрашивается', async () => {
	const sides = new SideVersions<Slice>();
	const c = counting({ v1: null, v2: slice('2026-11-21T12:00:00Z', 115000) });

	await sides.load('local', 'v1', () => c.fetch('v1'));
	assert.equal(c.calls.length, 1);
	assert.equal(sides.get('local'), null);

	await sides.load('local', 'v1', () => c.fetch('v1'));
	assert.equal(c.calls.length, 1);

	await sides.load('local', 'v2', () => c.fetch('v2'));
	assert.equal(c.calls.length, 2);
	assert.equal(sides.get('local')?.price, 115000);
});

test('смена версии одной стороны не перезагружает другую', async () => {
	const sides = new SideVersions<Slice>();
	const cloud = counting({ c1: slice('2026-11-21T10:00:00Z', 120000), c2: slice('2026-11-21T12:00:00Z', 110000) });
	const local = counting({ l1: slice('2026-11-21T09:00:00Z', 121000) });

	await sides.load('cloud', 'c1', () => cloud.fetch('c1'));
	await sides.load('local', 'l1', () => local.fetch('l1'));
	assert.deepEqual(cloud.calls, ['c1']);
	assert.deepEqual(local.calls, ['l1']);

	await sides.load('cloud', 'c2', () => cloud.fetch('c2'));
	await sides.load('local', 'l1', () => local.fetch('l1'));
	assert.deepEqual(cloud.calls, ['c1', 'c2']);
	assert.deepEqual(local.calls, ['l1']); // local не перезагружался
	assert.equal(sides.get('cloud')?.price, 110000);
	assert.equal(sides.get('local')?.price, 121000);
});

test('запоздавший ответ старой версии не замещает новую', async () => {
	const sides = new SideVersions<Slice>();
	let resolveOld: ((v: Slice | null) => void) | undefined;
	const old = new Promise<Slice | null>((resolve) => {
		resolveOld = resolve;
	});

	const first = sides.load('cloud', 'v1', () => old);
	await sides.load('cloud', 'v2', async () => slice('2026-11-21T12:00:00Z', 115000));
	assert.equal(sides.get('cloud')?.price, 115000);

	resolveOld!(slice('2026-11-21T10:00:00Z', 120000));
	await first;
	assert.equal(sides.get('cloud')?.price, 115000);
});
