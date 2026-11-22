import type {
	CatalogHistoryFile,
	CatalogIndex,
	CatalogManifest,
	CatalogManifestEntry,
	DashboardData,
	HistoryRow,
	ShopSource
} from '../types';

/** Функция загрузки подменяется в тестах — подсчёт обращений по URL. */
export type FetchLike = (input: string, init?: { cache?: 'no-cache' }) => Promise<Response>;

/**
 * Привязка магазина к источнику: та же сторона, что выбрал бы mergeSnapshots —
 * магазины из local.shops с last_crawl обслуживает local, остальные cloud.
 */
export interface ShopSourceBinding {
	side: ShopSource;
	/** last_crawl выбранной стороны из её latest: манифест привязан к этой метке. */
	last_crawl: string;
	/** Запись манифеста выбранной стороны; null — у стороны нет catalog-v2 (только Stage 1). */
	entry: CatalogManifestEntry | null;
	/** last_crawl latest и манифеста расходятся — данные нужно один раз перевалидировать. */
	mismatch: boolean;
}

/**
 * Выбирает источник для каждого магазина. Обновлённый `updated_at` дашборда
 * версией магазина не является: у каждого магазина своя метка last_crawl.
 */
export function selectShopSources(
	cloudLatest: DashboardData | null,
	localLatest: DashboardData | null,
	cloudManifest: CatalogManifest | null,
	localManifest: CatalogManifest | null
): Map<string, ShopSourceBinding> {
	const sources = new Map<string, ShopSourceBinding>();
	const localShops = new Set((localLatest?.shops ?? []).filter((s) => s.last_crawl).map((s) => s.name));
	const bind = (shop: string, side: ShopSource, latest: DashboardData | null, manifest: CatalogManifest | null) => {
		const status = latest?.shops.find((s) => s.name === shop);
		if (!status?.last_crawl) return; // сторона магазин не обходила — источника нет
		const entry = manifest?.shops?.[shop] ?? null;
		sources.set(shop, {
			side,
			last_crawl: status.last_crawl,
			entry,
			mismatch: !!entry && entry.last_crawl !== status.last_crawl
		});
	};
	for (const s of localLatest?.shops ?? []) if (localShops.has(s.name)) bind(s.name, 'local', localLatest, localManifest);
	for (const s of cloudLatest?.shops ?? []) if (!sources.has(s.name)) bind(s.name, 'cloud', cloudLatest, cloudManifest);
	return sources;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
	const buf = new ArrayBuffer(bytes.byteLength);
	new Uint8Array(buf).set(bytes);
	const digest = await crypto.subtle.digest('SHA-256', buf);
	return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export interface CatalogLoader {
	/** Перечитывает маленькие файлы (latest и манифесты обеих сторон) и пересобирает источники. */
	refreshSources(): Promise<Map<string, ShopSourceBinding>>;
	/** Привязка магазина к источнику; null — у магазина нет источника. */
	getSource(shop: string): Promise<ShopSourceBinding | null>;
	loadIndex(shop: string): Promise<CatalogIndex | null>;
	loadHistory(shop: string, sku: string): Promise<HistoryRow | null>;
}

type BigKind = 'index' | 'history';

/** Чистый (без рун и $app) загрузчик catalog-v2: кэш и in-flight промисы ключуются
 * стороной, магазином, типом ресурса и хешем версии. */
class HttpCatalogLoader implements CatalogLoader {
	private sources: Map<string, ShopSourceBinding> | null = null;
	private sourcesPending: Promise<Map<string, ShopSourceBinding>> | null = null;
	private sourcesGen = 0;
	private indexCache = new Map<string, CatalogIndex>();
	private historyCache = new Map<string, CatalogHistoryFile>();
	private pending = new Map<string, Promise<unknown>>();

	private fetchFn: FetchLike;
	private base: string;

	constructor(fetchFn: FetchLike, base: string) {
		this.fetchFn = fetchFn;
		this.base = base;
	}

	/** Маленькие файлы: свежесть через HTTP revalidation (cache: 'no-cache'). */
	private async fetchSmall<T>(path: string): Promise<T | null> {
		const res = await this.fetchFn(`${this.base}/data/${path}`, { cache: 'no-cache' });
		if (res.status === 404) return null;
		if (!res.ok) throw new Error(`HTTP ${res.status}`);
		return (await res.json()) as T;
	}

	refreshSources(): Promise<Map<string, ShopSourceBinding>> {
		if (this.sourcesPending) return this.sourcesPending;
		const gen = ++this.sourcesGen;
		const request = (async () => {
			const [cloudLatest, localLatest, cloudManifest, localManifest] = await Promise.all([
				this.fetchSmall<DashboardData>('latest.json'),
				this.fetchSmall<DashboardData>('local/latest.json').catch(() => null),
				this.fetchSmall<CatalogManifest>('catalog-v2/manifest.json').catch(() => null),
				this.fetchSmall<CatalogManifest>('local/catalog-v2/manifest.json').catch(() => null)
			]);
			// Запоздавший ответ не замещает источники, собранные более свежим запросом.
			if (gen !== this.sourcesGen) return this.sources ?? new Map<string, ShopSourceBinding>();
			const sources = selectShopSources(cloudLatest, localLatest, cloudManifest, localManifest);
			this.sources = sources;
			return sources;
		})().finally(() => {
			if (this.sourcesPending === request) this.sourcesPending = null;
		});
		this.sourcesPending = request;
		return request;
	}

	async getSource(shop: string): Promise<ShopSourceBinding | null> {
		let sources = this.sources ?? (await this.refreshSources());
		let binding = sources.get(shop) ?? null;
		if (binding?.mismatch) {
			// Метки latest и манифеста расходятся: один раз перевалидировать маленькие файлы.
			sources = await this.refreshSources();
			binding = sources.get(shop) ?? null;
		}
		return binding;
	}

	async loadIndex(shop: string): Promise<CatalogIndex | null> {
		return (await this.loadBig(shop, 'index')) as CatalogIndex | null;
	}

	async loadHistory(shop: string, sku: string): Promise<HistoryRow | null> {
		const file = (await this.loadBig(shop, 'history')) as CatalogHistoryFile | null;
		return file?.items[sku] ?? null;
	}

	private async loadBig(shop: string, kind: BigKind): Promise<CatalogIndex | CatalogHistoryFile | null> {
		const binding = await this.getSource(shop);
		if (!binding?.entry) return null; // только Stage 1: витрина и legacy-история
		const hash = kind === 'index' ? binding.entry.index_sha256 : binding.entry.history_sha256;
		const key = `${binding.side}|${shop}|${kind}|${hash}`;
		const cache: Map<string, CatalogIndex | CatalogHistoryFile> =
			kind === 'index' ? this.indexCache : this.historyCache;
		const cached = cache.get(key);
		if (cached) return cached;
		const inflight = this.pending.get(key);
		if (inflight) return inflight as Promise<CatalogIndex | CatalogHistoryFile | null>;
		const request = this.fetchVerified(shop, binding, kind);
		this.pending.set(key, request);
		try {
			const data = await request;
			if (data) cache.set(key, data);
			return data;
		} finally {
			// После сбоя удалять неудачный promise: следующий вызов повторит загрузку.
			if (this.pending.get(key) === request) this.pending.delete(key);
		}
	}

	/** Скачивает большой файл, проверяет хеш байтов, schema и shop до попадания в кэш.
	 * При 404 или несовпадении хеша — один раз обновить манифест и повторить. */
	private async fetchVerified(
		shop: string,
		binding: ShopSourceBinding,
		kind: BigKind,
		retried = false
	): Promise<CatalogIndex | CatalogHistoryFile | null> {
		const entry = binding.entry!;
		const hash = kind === 'index' ? entry.index_sha256 : entry.history_sha256;
		const prefix = binding.side === 'local' ? 'local/' : '';
		// Большие файлы: версия в URL (?v=<hash>), содержимое по хешу неизменно.
		const url = `${this.base}/data/${prefix}catalog-v2/${encodeURIComponent(shop)}/${kind}.json?v=${hash}`;
		const res = await this.fetchFn(url);
		if (res.status !== 404 && !res.ok) throw new Error(`HTTP ${res.status}`);
		const bytes = res.status === 404 ? null : new Uint8Array(await res.arrayBuffer());
		const actual = bytes ? await sha256Hex(bytes) : null;
		if (res.status === 404 || actual !== hash) {
			if (retried) {
				if (res.status === 404) return null; // манифест всё ещё обещает — данных нет, только Stage 1
				throw new Error(`хеш ${kind}.json магазина ${shop} не совпал с манифестом`);
			}
			const sources = await this.refreshSources();
			const fresh = sources.get(shop) ?? null;
			if (!fresh?.entry) return null;
			return this.fetchVerified(shop, fresh, kind, true);
		}
		const parsed = JSON.parse(new TextDecoder().decode(bytes!)) as CatalogIndex | CatalogHistoryFile;
		if (parsed.schema !== 2 || parsed.shop !== shop) {
			throw new Error(`${kind}.json магазина ${shop}: неожиданная схема или магазин`);
		}
		return parsed;
	}
}

export function createCatalogLoader(fetchFn: FetchLike, base: string): CatalogLoader {
	return new HttpCatalogLoader(fetchFn, base);
}
