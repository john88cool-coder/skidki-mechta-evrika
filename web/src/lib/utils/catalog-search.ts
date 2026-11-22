import type { CatalogIndex, CatalogRow } from '../types';
import type { CatalogLoader, ShopSourceBinding } from './catalog-source';

/**
 * Чистый поиск по строкам catalog-v2. Сеть не трогает: вход — уже загруженные
 * строки индексов; вставленная ссылка только сравнивается с адресами товаров.
 */
export type TextQuery = { kind: 'text'; words: string[]; raw: string };
export type UrlQuery = { kind: 'url'; host: string; path: string; params: string };

/** NFKC, нижний регистр, ё → е, схлопнуть пробелы. */
export function normalizeText(value: string): string {
	return value.normalize('NFKC').toLowerCase().replaceAll('ё', 'е').replace(/\s+/g, ' ').trim();
}

/** Параметры, которые не влияют на товар: только их и убираем из ссылки. */
const TRACKING_PARAMS = ['gclid', 'fbclid', 'yclid', 'msclkid', '_openstat', 'spm'];

function isTracking(name: string): boolean {
	return /^utm_/i.test(name) || TRACKING_PARAMS.includes(name.toLowerCase());
}

/**
 * Нормализует вставленную ссылку: убирает fragment, tracking-параметры и
 * завершающий «/» пути. Произвольная строка со схемой в середине текста —
 * не ссылка (SKU из неё не извлекаем).
 */
export function parseUrlQuery(raw: string): UrlQuery | null {
	const trimmed = raw.trim();
	if (!trimmed || /\s/.test(trimmed)) return null;
	let candidate = trimmed;
	if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(candidate)) {
		// Ссылка без схемы — только если похоже на host/path.
		if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+(\/|$)/i.test(candidate)) return null;
		candidate = `https://${candidate}`;
	}
	let url: URL;
	try {
		url = new URL(candidate);
	} catch {
		return null;
	}
	if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
	const params = [...url.searchParams.entries()]
		.filter(([name]) => !isTracking(name))
		.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
	return {
		kind: 'url',
		host: url.host.toLowerCase(),
		path: url.pathname.replace(/\/+$/, ''),
		params: JSON.stringify(params)
	};
}

function normalizeProductUrl(raw: string): UrlQuery | null {
	const parsed = parseUrlQuery(raw);
	if (parsed) return parsed;
	// Адреса товаров без схемы (например «//host/path» или относительные) не сравниваем.
	try {
		const url = new URL(raw);
		if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
		const params = [...url.searchParams.entries()]
			.filter(([name]) => !isTracking(name))
			.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
		return { kind: 'url', host: url.host.toLowerCase(), path: url.pathname.replace(/\/+$/, ''), params: JSON.stringify(params) };
	} catch {
		return null;
	}
}

/** Класс совпадения: сначала точный URL, затем точные SKU/MPN, затем все слова. */
const TIER_URL = 0;
const TIER_EXACT = 1;
const TIER_WORDS = 2;

interface Match {
	row: CatalogRow;
	tier: number;
	/** Насколько «прямое» совпадение по словам: меньше лишних слов — лучше. */
	extraWords: number;
}

function exactSkuOrMpn(row: CatalogRow, needle: string): boolean {
	const sku = normalizeText(row.product.sku);
	const mpn = row.product.mpn ? normalizeText(row.product.mpn) : null;
	return sku === needle || (!!mpn && mpn === needle);
}

function matchRow(row: CatalogRow, text: TextQuery, url: UrlQuery | null): Match | null {
	const p = row.product;
	if (url) {
		const target = normalizeProductUrl(p.url);
		if (target && target.host === url.host && target.path === url.path && target.params === url.params) {
			return { row, tier: TIER_URL, extraWords: 0 };
		}
		return null; // ссылка совпадает только целиком, по известным host/path/params
	}
	const needle = text.raw;
	if (exactSkuOrMpn(row, needle)) return { row, tier: TIER_EXACT, extraWords: 0 };
	const hay = normalizeText(`${p.title} ${p.brand ?? ''} ${p.mpn ?? ''}`);
	if (!text.words.every((w) => hay.includes(w))) return null;
	return { row, tier: TIER_WORDS, extraWords: hay.split(' ').length - text.words.length };
}

function compareMatches(a: Match, b: Match): number {
	if (a.tier !== b.tier) return a.tier - b.tier;
	if (a.extraWords !== b.extraWords) return a.extraWords - b.extraWords;
	// Равная релевантность: доступные позиции впереди.
	const avail = Number(b.row.product.in_stock) - Number(a.row.product.in_stock);
	if (avail !== 0) return avail;
	// Последние ключи — цена, магазин, SKU.
	const price = (a.row.product.price ?? Infinity) - (b.row.product.price ?? Infinity);
	if (price !== 0) return price;
	const shop = a.row.product.shop.localeCompare(b.row.product.shop);
	if (shop !== 0) return shop;
	return a.row.product.sku.localeCompare(b.row.product.sku);
}

/**
 * Ищет по строкам каталога: точный URL → точные SKU/MPN → все нормализованные
 * слова по названию, бренду и модели. Пустая строка — пустой массив.
 */
export function searchCatalog(rows: CatalogRow[], query: string, limit: number): CatalogRow[] {
	const normalized = normalizeText(query);
	if (!normalized || limit <= 0) return [];
	const url = parseUrlQuery(query);
	const text: TextQuery = { kind: 'text', words: normalized.split(' '), raw: normalized };
	const matches: Match[] = [];
	for (const row of rows) {
		const m = matchRow(row, text, url);
		if (m) matches.push(m);
	}
	matches.sort(compareMatches);
	return matches.slice(0, limit).map((m) => m.row);
}

/** Параллельная обработка с ограничением одновременных задач (порядок сохраняется). */
export async function mapLimit<T, R>(
	items: T[],
	limit: number,
	fn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
	const out = new Array<R>(items.length);
	let next = 0;
	const workers = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
		while (next < items.length) {
			const index = next++;
			out[index] = await fn(items[index], index);
		}
	});
	await Promise.all(workers);
	return out;
}

/**
 * Однократный запуск работы: повторные вызовы до завершения возвращают тот же
 * промис — новое поколение не создаётся, состояние «работы идёт» не сбрасывается.
 * Успех мемоизируется; сбой сбрасывает врата — следующий вызов повторит попытку.
 */
export function createOnceGate<A>(start: () => Promise<A>): () => Promise<A> {
	let job: Promise<A> | null = null;
	return () => {
		if (job) return job;
		job = (async () => {
			try {
				return await start();
			} catch (error) {
				job = null; // сбой — разрешить повтор
				throw error;
			}
		})();
		return job;
	};
}

export interface GatherResult {
	/** Строки всех успешно загруженных индексов. */
	rows: CatalogRow[];
	/** Магазины с загруженным индексом. */
	ok: string[];
	/** Магазины, у которых есть только витрина Stage 1 (binding.entry === null). */
	showcaseOnly: string[];
	/** Магазины, чей индекс загрузить не удалось. */
	failed: string[];
}

export interface GatherOptions {
	/** Максимум одновременных загрузок индексов (по умолчанию 3). */
	concurrency?: number;
	/** Вызывается после готовности каждого магазина — список обновляется по мере загрузки. */
	onPartial?: (partial: GatherResult) => void;
}

/**
 * Собирает строки всех магазинов catalog-v2: маленькие файлы (sources), затем
 * индексы с ограничением одновременных запросов. Сеть не обращается к вставленной
 * ссылке — только загрузка индексов. Частичный отказ не прерывает остальные.
 */
export async function gatherRows(loader: CatalogLoader, options: GatherOptions = {}): Promise<GatherResult> {
	const sources = await loader.refreshSources();
	const shops = [...sources.keys()];
	const acc: GatherResult = { rows: [], ok: [], showcaseOnly: [], failed: [] };
	await mapLimit(shops, options.concurrency ?? 3, async (shop) => {
		const binding: ShopSourceBinding | null = await loader.getSource(shop);
		if (!binding?.entry) {
			if (binding) acc.showcaseOnly.push(shop);
			// Нет источника вовсе — магазин просто не участвует в поиске.
		} else {
			try {
				const index: CatalogIndex | null = await loader.loadIndex(shop);
				if (index) {
					acc.rows.push(...index.rows);
					acc.ok.push(shop);
				} else {
					acc.showcaseOnly.push(shop);
				}
			} catch {
				acc.failed.push(shop);
			}
		}
		options.onPartial?.({ rows: [...acc.rows], ok: [...acc.ok], showcaseOnly: [...acc.showcaseOnly], failed: [...acc.failed] });
	});
	return acc;
}
