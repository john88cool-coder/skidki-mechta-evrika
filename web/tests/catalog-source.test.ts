import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCatalogLoader, selectShopSources, type FetchLike } from '../src/lib/utils/catalog-source.ts';
import type { CatalogHistoryFile, CatalogIndex, CatalogManifest, DashboardData } from '../src/lib/types.ts';

const enc = (body: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(body));

async function sha256(bytes: Uint8Array): Promise<string> {
	const buf = new ArrayBuffer(bytes.byteLength);
	new Uint8Array(buf).set(bytes);
	const digest = await crypto.subtle.digest('SHA-256', buf);
	return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const notFound = () => new Response(null, { status: 404 });

const shopStatus = (name: string, last_crawl: string | null, item_count = 5) => ({
	name,
	label: name,
	last_crawl,
	item_count,
	status: (last_crawl ? 'ok' : 'error') as 'ok' | 'error'
});

const stats = { total_products: 10, total_deals: 0, avg_discount: 0 };

const CLOUD_LATEST: DashboardData = {
	updated_at: '2026-11-21T12:00:00Z',
	deals: [],
	shops: [
		shopStatus('mechta', '2026-11-21T12:00:00Z'),
		shopStatus('shopkz', '2026-11-21T09:00:00Z'),
		shopStatus('evrika', '2026-11-21T09:00:00Z', 0),
		shopStatus('technodom', null, 0)
	],
	stats
};

// Локальный обход mechta старше облачного — приоритет стороны от свежести не зависит.
const LOCAL_LATEST: DashboardData = {
	updated_at: '2026-11-21T10:00:00Z',
	deals: [],
	shops: [shopStatus('mechta', '2026-11-21T10:00:00Z'), shopStatus('evrika', null, 0)],
	stats
};

const MECHTA_INDEX: CatalogIndex = {
	schema: 2,
	shop: 'mechta',
	rows: [
		{
			product: { shop: 'mechta', sku: 'A:17', title: 'Demo Phone', price: 120000, url: '#', in_stock: true },
			last_seen: '2026-11-21T10:00:00Z',
			base_price: null,
			fair_discount: null,
			pump_price: null,
			exact_model: null
		}
	]
};
const MECHTA_HISTORY: CatalogHistoryFile = {
	schema: 2,
	shop: 'mechta',
	items: {
		'A:17': {
			points: [{ date: '2026-11-20', price: 120000 }],
			recent_points: [{ date: '2026-11-21T10:00:00Z', price: 120000, old_price: null }],
			min: 120000,
			median: 120000,
			days_at_current: 1,
			coverage_days: 2
		}
	}
};
const SHOPKZ_INDEX: CatalogIndex = { schema: 2, shop: 'shopkz', rows: [] };
const SHOPKZ_HISTORY_V1: CatalogHistoryFile = {
	schema: 2,
	shop: 'shopkz',
	items: {
		'77': {
			points: [{ date: '2026-11-20', price: 120000 }],
			recent_points: [],
			min: 120000,
			median: 120000,
			days_at_current: 1,
			coverage_days: 1
		}
	}
};
const SHOPKZ_HISTORY_V2: CatalogHistoryFile = {
	schema: 2,
	shop: 'shopkz',
	items: {
		'77': {
			points: [{ date: '2026-11-21', price: 115000 }],
			recent_points: [],
			min: 115000,
			median: 115000,
			days_at_current: 0,
			coverage_days: 1
		}
	}
};

async function manifestOf(
	entries: Record<string, { last_crawl: string; index: unknown; history: unknown }>
): Promise<CatalogManifest> {
	const shops: CatalogManifest['shops'] = {};
	for (const [shop, e] of Object.entries(entries)) {
		shops[shop] = {
			last_crawl: e.last_crawl,
			count: 1,
			index_sha256: await sha256(enc(e.index)),
			history_sha256: await sha256(enc(e.history))
		};
	}
	return { schema: 2, shops };
}

interface BigRoute {
	(): Response | Promise<Response>;
}
interface Routes {
	cloudLatest?: unknown;
	localLatest?: unknown;
	cloudManifest?: unknown;
	localManifest?: unknown;
	big: Map<string, Response | Promise<Response> | BigRoute>;
}

function makeFetch(routes: Routes) {
	const calls: { url: string; cache?: string }[] = [];
	const fetchFn: FetchLike = async (url, init) => {
		calls.push({ url, cache: init?.cache });
		if (url === '/data/latest.json') return routes.cloudLatest === undefined ? notFound() : ok(routes.cloudLatest);
		if (url === '/data/local/latest.json') return routes.localLatest === undefined ? notFound() : ok(routes.localLatest);
		if (url === '/data/catalog-v2/manifest.json')
			return routes.cloudManifest === undefined ? notFound() : ok(routes.cloudManifest);
		if (url === '/data/local/catalog-v2/manifest.json')
			return routes.localManifest === undefined ? notFound() : ok(routes.localManifest);
		const route = routes.big.get(url);
		if (route) return typeof route === 'function' ? route() : route;
		return notFound();
	};
	return {
		calls,
		fetchFn,
		count: (substr: string) => calls.filter((c) => c.url.includes(substr)).length
	};
}

async function fixtures() {
	const cloudManifest = await manifestOf({
		mechta: { last_crawl: '2026-11-21T12:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY },
		shopkz: { last_crawl: '2026-11-21T09:00:00Z', index: SHOPKZ_INDEX, history: SHOPKZ_HISTORY_V1 }
	});
	const localManifest = await manifestOf({
		mechta: { last_crawl: '2026-11-21T10:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY }
	});
	return {
		cloudManifest,
		localManifest,
		mechtaIndexHash: cloudManifest.shops.mechta.index_sha256,
		mechtaHash: cloudManifest.shops.mechta.history_sha256,
		shopkzHash: cloudManifest.shops.shopkz.history_sha256
	};
}

test('селектор: stale local выигрывает, манифест и last_crawl — от выбранной стороны', async () => {
	const f = await fixtures();
	const sources = selectShopSources(CLOUD_LATEST, LOCAL_LATEST, f.cloudManifest, f.localManifest);
	const mechta = sources.get('mechta')!;
	assert.equal(mechta.side, 'local');
	// локальный обход (10:00) старше облачного (12:00), но правило merge — приоритет у local
	assert.equal(mechta.last_crawl, '2026-11-21T10:00:00Z');
	assert.equal(mechta.entry, f.localManifest.shops.mechta);
	assert.equal(mechta.mismatch, false);
});

test('селектор: cloud-only, local без обхода и магазин без источника', async () => {
	const f = await fixtures();
	const sources = selectShopSources(CLOUD_LATEST, LOCAL_LATEST, f.cloudManifest, f.localManifest);
	const shopkz = sources.get('shopkz')!;
	assert.equal(shopkz.side, 'cloud');
	assert.equal(shopkz.last_crawl, '2026-11-21T09:00:00Z');
	// evrika есть в local, но без last_crawl — работает облачный источник
	assert.equal(sources.get('evrika')!.side, 'cloud');
	// technodom в cloud без успешного обхода — источника нет вовсе
	assert.equal(sources.has('technodom'), false);
});

test('селектор: расхождение last_crawl манифеста и latest помечается как mismatch', async () => {
	const stale = await manifestOf({
		mechta: { last_crawl: '2026-11-01T00:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY }
	});
	const sources = selectShopSources(CLOUD_LATEST, null, stale, null);
	assert.equal(sources.get('mechta')!.mismatch, true);
});

test('cloud-only: индекс из облачного catalog-v2, локальные большие файлы не запрашиваются', async () => {
	const f = await fixtures();
	const r = makeFetch({
		cloudLatest: CLOUD_LATEST,
		cloudManifest: f.cloudManifest,
		big: new Map([[`/data/catalog-v2/mechta/index.json?v=${f.mechtaIndexHash}`, ok(MECHTA_INDEX)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	const index = await loader.loadIndex('mechta');
	assert.equal(index?.rows[0]?.product.sku, 'A:17');
	assert.equal(r.count(`/data/catalog-v2/mechta/index.json?v=${f.mechtaIndexHash}`), 1);
	assert.equal(r.count('/data/local/catalog-v2/mechta/'), 0);
	// маленькие файлы — с HTTP revalidation, большие — версионированный URL без no-cache
	assert.equal(r.calls.find((c) => c.url === '/data/latest.json')?.cache, 'no-cache');
	assert.equal(r.calls.find((c) => c.url.includes('/catalog-v2/mechta/index.json'))?.cache, undefined);
});

test('local-only: облако не опубликовано — mechta из local/catalog-v2', async () => {
	const f = await fixtures();
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: f.localManifest,
		big: new Map([[`/data/local/catalog-v2/mechta/index.json?v=${f.mechtaIndexHash}`, ok(MECHTA_INDEX)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	const index = await loader.loadIndex('mechta');
	assert.equal(index?.rows[0]?.product.sku, 'A:17');
	assert.equal(r.count(`/data/local/catalog-v2/mechta/index.json?v=${f.mechtaIndexHash}`), 1);
	assert.equal(r.count('/data/catalog-v2/mechta/'), 0);
});

test('одна сторона v1: манифеста нет — больших файлов нет, источник Stage 1', async () => {
	const r = makeFetch({ localLatest: LOCAL_LATEST, big: new Map() });
	const loader = createCatalogLoader(r.fetchFn, '');
	assert.equal(await loader.loadIndex('mechta'), null);
	assert.equal(await loader.loadHistory('mechta', 'A:17'), null);
	assert.equal(r.count('catalog-v2/mechta/'), 0);
});

test('пустой v2 магазин: пустой индекс валиден, история позиции отсутствует', async () => {
	const evrikaIndex: CatalogIndex = { schema: 2, shop: 'evrika', rows: [] };
	const evrikaHistory: CatalogHistoryFile = { schema: 2, shop: 'evrika', items: {} };
	const indexHash = await sha256(enc(evrikaIndex));
	const historyHash = await sha256(enc(evrikaHistory));
	const m = await manifestOf({
		evrika: { last_crawl: '2026-11-21T09:00:00Z', index: evrikaIndex, history: evrikaHistory }
	});
	const r = makeFetch({
		cloudLatest: CLOUD_LATEST,
		cloudManifest: m,
		big: new Map([
			[`/data/catalog-v2/evrika/index.json?v=${indexHash}`, ok(evrikaIndex)],
			[`/data/catalog-v2/evrika/history.json?v=${historyHash}`, ok(evrikaHistory)]
		])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	assert.deepEqual((await loader.loadIndex('evrika'))?.rows, []);
	assert.equal(await loader.loadHistory('evrika', 'NOPE'), null);
	assert.equal(r.count('catalog-v2/evrika/index.json'), 1);
	assert.equal(r.count('catalog-v2/evrika/history.json'), 1);
});

test('v2-история отдаёт свои имена полей: min/median, без legacy min_90d', async () => {
	const f = await fixtures();
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: f.localManifest,
		big: new Map([[`/data/local/catalog-v2/mechta/history.json?v=${f.mechtaHash}`, ok(MECHTA_HISTORY)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	const row = await loader.loadHistory('mechta', 'A:17');
	assert.equal(row?.min, 120000);
	assert.equal(row?.median, 120000);
	assert.equal(row?.days_at_current, 1);
	assert.equal(row && 'min_90d' in row, false);
});

test('ошибка загрузки: неудачный promise удаляется, повторный вызов ходит в сеть снова', async () => {
	const f = await fixtures();
	let fail = true;
	let historyCalls = 0;
	const url = `/data/local/catalog-v2/mechta/history.json?v=${f.mechtaHash}`;
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: f.localManifest,
		big: new Map([
			[
				url,
				() => {
					historyCalls += 1;
					return fail ? new Response('boom', { status: 500 }) : ok(MECHTA_HISTORY);
				}
			]
		])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	await assert.rejects(loader.loadHistory('mechta', 'A:17'), /HTTP 500/);
	// сбой сети не инвалидирует источники: маленькие файлы не пере запрашивались
	assert.equal(r.count('manifest.json'), 2);
	fail = false;
	const row = await loader.loadHistory('mechta', 'A:17');
	assert.equal(row?.min, 120000);
	assert.equal(historyCalls, 2);
});

test('несовпадение хеша: один раз перевалидировать манифест и повторить, затем ошибка', async () => {
	const f = await fixtures();
	const bad: CatalogManifest = {
		schema: 2,
		shops: { mechta: { ...f.localManifest.shops.mechta, history_sha256: '0'.repeat(64) } }
	};
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: bad,
		// Response одноразовый: каждый запрос получает свежий экземпляр
		big: new Map([[`/data/local/catalog-v2/mechta/history.json?v=${'0'.repeat(64)}`, () => ok(MECHTA_HISTORY)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	await assert.rejects(loader.loadHistory('mechta', 'A:17'), /хеш/);
	assert.equal(r.count('catalog-v2/mechta/history.json'), 2);
	// перевалидация манифеста — ровно один раз
	assert.equal(r.count('local/catalog-v2/manifest.json'), 2);
});

test('несовпадение меток latest и манифеста: один раз перевалидировать и работать по хешам', async () => {
	const f = await fixtures();
	const stale = await manifestOf({
		mechta: { last_crawl: '2026-11-01T00:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY }
	});
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: stale,
		big: new Map([[`/data/local/catalog-v2/mechta/history.json?v=${f.mechtaHash}`, ok(MECHTA_HISTORY)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	const row = await loader.loadHistory('mechta', 'A:17');
	assert.equal(row?.min, 120000);
	assert.equal(r.count('local/catalog-v2/manifest.json'), 2);
	assert.equal(r.count('catalog-v2/mechta/history.json'), 1);
});

test('два одновременных loadHistory — одна загрузка файла', async () => {
	const f = await fixtures();
	const r = makeFetch({
		localLatest: LOCAL_LATEST,
		localManifest: f.localManifest,
		big: new Map([[`/data/local/catalog-v2/mechta/history.json?v=${f.mechtaHash}`, ok(MECHTA_HISTORY)]])
	});
	const loader = createCatalogLoader(r.fetchFn, '');
	const [a, b] = await Promise.all([
		loader.loadHistory('mechta', 'A:17'),
		loader.loadHistory('mechta', 'A:17')
	]);
	assert.equal(a?.points.length, 1);
	assert.deepEqual(b, a);
	assert.equal(r.count('catalog-v2/mechta/history.json'), 1);
});

test('смена версии во время запроса: запоздавший ответ не замещает новое состояние', async () => {
	const f = await fixtures();
	let resolveA: ((r: Response) => void) | undefined;
	const pendingA = new Promise<Response>((resolve) => {
		resolveA = resolve;
	});
	const urlA = `/data/catalog-v2/shopkz/history.json?v=${f.shopkzHash}`;
	const v2Hash = await sha256(enc(SHOPKZ_HISTORY_V2));
	const urlB = `/data/catalog-v2/shopkz/history.json?v=${v2Hash}`;
	const routes: Routes = {
		cloudLatest: CLOUD_LATEST,
		cloudManifest: f.cloudManifest,
		big: new Map<string, Response | Promise<Response> | BigRoute>([
			[urlA, pendingA],
			[urlB, ok(SHOPKZ_HISTORY_V2)]
		])
	};
	const r = makeFetch(routes);
	const loader = createCatalogLoader(r.fetchFn, '');
	const first = loader.loadHistory('shopkz', '77');
	// пока первый запрос в полёте, публикуется новая версия манифеста
	routes.cloudManifest = await manifestOf({
		mechta: { last_crawl: '2026-11-21T12:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY },
		shopkz: { last_crawl: '2026-11-21T13:00:00Z', index: SHOPKZ_INDEX, history: SHOPKZ_HISTORY_V2 }
	});
	await loader.refreshSources();
	const second = await loader.loadHistory('shopkz', '77');
	assert.equal(second?.points[0]?.price, 115000);
	resolveA!(ok(SHOPKZ_HISTORY_V1));
	const stale = await first;
	assert.equal(stale?.points[0]?.price, 120000);
	// состояние загрузчика — новая версия: повторный вызов не ходит в сеть
	const cached = await loader.loadHistory('shopkz', '77');
	assert.equal(cached?.points[0]?.price, 115000);
	assert.equal(r.count(urlA), 1);
	assert.equal(r.count(urlB), 1);
});

test('изменение версии shopkz не сбрасывает mechta', async () => {
	const f = await fixtures();
	const urlM = `/data/local/catalog-v2/mechta/history.json?v=${f.mechtaHash}`;
	const urlS = `/data/catalog-v2/shopkz/history.json?v=${f.shopkzHash}`;
	const v2Hash = await sha256(enc(SHOPKZ_HISTORY_V2));
	const routes: Routes = {
		cloudLatest: CLOUD_LATEST,
		localLatest: LOCAL_LATEST,
		cloudManifest: f.cloudManifest,
		localManifest: f.localManifest,
		big: new Map<string, Response | Promise<Response> | BigRoute>([
			[urlM, ok(MECHTA_HISTORY)],
			[urlS, ok(SHOPKZ_HISTORY_V1)],
			[`/data/catalog-v2/shopkz/history.json?v=${v2Hash}`, ok(SHOPKZ_HISTORY_V2)]
		])
	};
	const r = makeFetch(routes);
	const loader = createCatalogLoader(r.fetchFn, '');
	assert.equal((await loader.loadHistory('mechta', 'A:17'))?.min, 120000);
	// новая публикация: shopkz переехал на новую версию, mechta не менялся
	routes.cloudManifest = await manifestOf({
		mechta: { last_crawl: '2026-11-21T12:00:00Z', index: MECHTA_INDEX, history: MECHTA_HISTORY },
		shopkz: { last_crawl: '2026-11-21T13:00:00Z', index: SHOPKZ_INDEX, history: SHOPKZ_HISTORY_V2 }
	});
	await loader.refreshSources();
	assert.equal((await loader.loadHistory('mechta', 'A:17'))?.min, 120000);
	assert.equal(r.count(urlM), 1);
	const v2Hash2 = await sha256(enc(SHOPKZ_HISTORY_V2));
	assert.equal((await loader.loadHistory('shopkz', '77'))?.points[0]?.price, 115000);
	assert.equal(r.count(`/data/catalog-v2/shopkz/history.json?v=${v2Hash2}`), 1);
});
