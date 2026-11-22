import { formatPrice } from './format.ts';
import { verdictOf, type Verdict } from './verdict.ts';
import type { CatalogIndex, CatalogRow, Deal, HistoryRow, PricePoint, Product, ProductHistory } from '../types';

export interface RecentPrice extends PricePoint { change: number | null }

/** Calculate against the preceding observation BEFORE trimming the visible window. */
export function recentPrices(points: PricePoint[], limit = 5): RecentPrice[] {
	const valid = points.filter((point) => Number.isFinite(point.price) && point.price > 0);
	return valid.map((point, index) => ({
		...point,
		change: index ? ((point.price - valid[index - 1].price) / valid[index - 1].price) * 100 : null
	})).slice(-Math.max(1, limit));
}

export function formatChange(change: number | null): string {
	if (change === null) return '—';
	if (change === 0) return '0%';
	const magnitude = Math.abs(change);
	const value = magnitude < 0.1 ? '<0,1' : magnitude.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
	return `${change < 0 ? '−' : '+'}${value}%`;
}

/** Считает длительность непрерывного удержания текущей цены в полных сутках. */
export function computeDaysAtCurrent(points: PricePoint[], nowMs = Date.now()): number {
	const valid = points.filter((p) => Number.isFinite(p.price) && p.price > 0);
	if (!valid.length) return 0;
	const currentPrice = valid[valid.length - 1].price;
	let earliest = valid[valid.length - 1].date;
	for (let i = valid.length - 1; i >= 0; i -= 1) {
		if (valid[i].price !== currentPrice) break;
		earliest = valid[i].date;
	}
	const parsed = Date.parse(earliest);
	if (!Number.isFinite(parsed)) return 0;
	return Math.max(0, Math.floor((nowMs - parsed) / 86_400_000));
}

/** Собирает карточку товара вне текущего топ-300 по снимку и последней точке истории. */
export function buildFallbackProduct(
	shop: string,
	sku: string,
	points: PricePoint[],
	snapshot: Product | null
): Product {
	const last = points[points.length - 1];
	if (snapshot) {
		return {
			...snapshot,
			shop,
			sku,
			price: last?.price ?? snapshot.price,
			old_price: last?.old_price ?? snapshot.old_price ?? null
		};
	}
	return {
		shop,
		sku,
		title: `${shop} · ${sku}`,
		price: last?.price ?? 0,
		old_price: last?.old_price ?? null,
		url: '',
		in_stock: true
	};
}

/** Выгода от «обычной цены»: одна база на всю страницу товара. Нет базы или разница до 1% — null. */
export function baseDelta(price: number, base: number | null | undefined): { delta: number; pct: number } | null {
	if (!base || !Number.isFinite(base) || base <= price * 1.01) return null;
	return { delta: base - price, pct: ((base - price) / base) * 100 };
}

/* ================= Карточка товара без акции (задача 5) ================= */

/** Сколько дней накопленной истории достаточно, чтобы сравнивать цену с обычной. */
export const MIN_COVERAGE_DAYS = 3;

/** Откуда получена карточка: catalog-v2, старый срез или снимок избранного. */
export type ItemSource = 'catalog-v2' | 'legacy' | 'favorites';

export interface ItemStats {
	min90d: number | null;
	median30d: number | null;
	daysAtCurrent: number | null;
}

/** Нормализованная карточка товара для страницы товара. */
export interface ItemCard {
	source: ItemSource;
	product: Product;
	/** Обычная цена: base_price витрины/каталога или median 30д среза; null — неизвестна. */
	basePrice: number | null;
	/** Точки истории; может быть пусто — график не показываем. */
	points: PricePoint[];
	recent: PricePoint[];
	stats: ItemStats | null;
	/** Дата последнего наблюдения из catalog-v2 (для выбывших позиций). */
	lastSeen: string | null;
	/** Дата первого наблюдения в наличии из выборки history.json («наблюдаем с»); null — нет. */
	firstStocked: string | null;
	/** Дней накопленной истории; null — истории нет вовсе. */
	coverageDays: number | null;
}

export type ItemLoad =
	| { status: 'found'; card: ItemCard }
	| { status: 'missing' }
	| { status: 'unavailable'; reason: string }
	/** Ответ устаревшей пары при быстром переходе A → B — не применяется. */
	| { status: 'stale' };

/** Источники карточки; подменяются в тестах. */
export interface ItemDeps {
	/** catalog-v2: индекс, история и источник магазина по точной паре (shop, sku). */
	loader: {
		loadIndex(shop: string): Promise<CatalogIndex | null>;
		loadHistory(shop: string, sku: string): Promise<HistoryRow | null>;
		/** Привязка магазина к источнику; null — источника нет. */
		getSource(shop: string): Promise<{ last_crawl: string } | null>;
	};
	/** Старый срез: существующий путь через fetchHistory. */
	fetchHistory: (shop: string, sku: string) => Promise<ProductHistory | null>;
	/** Сохранённая копия избранного. */
	snapshot: (id: string) => Product | null;
}

/** Дней наблюдений между первой и последней точкой — для legacy-среза без coverage_days. */
export function coverageFromPoints(points: PricePoint[]): number | null {
	if (!points.length) return null;
	const first = Date.parse(points[0].date);
	const last = Date.parse(points[points.length - 1].date);
	if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
	return Math.max(1, Math.floor((last - first) / 86_400_000) + 1);
}

/**
 * Покрытие карточки из записи catalog-v2. Новые файлы: точные часы от
 * first_stocked до времени оценки среза (last_crawl выбранного источника
 * магазина) — 71:59 даёт 2,99, 72:00 ровно 3. Старые файлы без first_stocked:
 * готовое числовое coverage_days от момента их выпуска, как раньше.
 */
export function coverageFromRow(history: HistoryRow | null, evalTime: string | null): number | null {
	if (!history) return null;
	if (history.first_stocked !== undefined) {
		if (!history.first_stocked || !evalTime) return null;
		const first = Date.parse(history.first_stocked);
		const at = Date.parse(evalTime);
		if (!Number.isFinite(first) || !Number.isFinite(at) || at < first) return null;
		return (at - first) / 86_400_000;
	}
	return typeof history.coverage_days === 'number' ? history.coverage_days : null;
}

function cardFromRow(row: CatalogRow, history: HistoryRow | null, evalTime: string | null): ItemCard {
	const points = history?.points ?? [];
	return {
		source: 'catalog-v2',
		product: row.product,
		basePrice: row.base_price,
		points,
		recent: history?.recent_points ?? points,
		stats: history
			? { min90d: history.min, median30d: history.median, daysAtCurrent: history.days_at_current }
			: null,
		lastSeen: row.last_seen,
		// Дата из той же выборки отрезков, что точки графика; для старых файлов — null.
		firstStocked: history?.first_stocked ? history.first_stocked.slice(0, 10) : null,
		coverageDays: coverageFromRow(history, evalTime)
	};
}

function cardFromLegacy(legacy: ProductHistory): ItemCard {
	const median = legacy.stats.median_30d;
	return {
		source: 'legacy',
		product: legacy.product,
		basePrice: median > 0 ? median : null,
		points: legacy.history,
		recent: legacy.recent ?? legacy.history,
		stats: {
			min90d: legacy.stats.min_90d,
			median30d: median,
			daysAtCurrent: legacy.stats.days_at_current
		},
		lastSeen: null,
		firstStocked: null,
		coverageDays: coverageFromPoints(legacy.history)
	};
}

function cardFromFavorites(product: Product): ItemCard {
	return {
		source: 'favorites',
		product,
		basePrice: null,
		points: [],
		recent: [],
		stats: null,
		lastSeen: null,
		firstStocked: null,
		coverageDays: null
	};
}

/**
 * Полный путь загрузки карточки: catalog-v2 → старый срез (существующий путь
 * через fetchHistory) → сохранённая копия избранного.
 *
 * Каждый ответ применяется только для активной пары: при быстром переходе
 * A → B устаревший ответ получает статус 'stale' и содержимое не меняет.
 * Сбой сети даёт 'unavailable' — тот же товар можно запросить повторно.
 */
export async function loadItemCard(
	deps: ItemDeps,
	shop: string,
	sku: string,
	isActive: () => boolean = () => true
): Promise<ItemLoad> {
	let catalogReason: string | null = null;
	try {
		const index = await deps.loader.loadIndex(shop);
		if (!isActive()) return { status: 'stale' };
		const row = index ? (index.rows.find((r) => r.product.sku === sku) ?? null) : null;
		if (row) {
			const history = await deps.loader.loadHistory(shop, sku);
			if (!isActive()) return { status: 'stale' };
			// Время оценки среза — last_crawl выбранного источника магазина из биндинга;
			// биндинг уже загружен (loadHistory строит URL по хешу манифеста), поэтому
			// часы браузера не участвуют.
			const binding = await deps.loader.getSource(shop).catch(() => null);
			if (!isActive()) return { status: 'stale' };
			return { status: 'found', card: cardFromRow(row, history, binding?.last_crawl ?? null) };
		}
	} catch (e) {
		catalogReason = e instanceof Error ? e.message : String(e);
	}
	if (!isActive()) return { status: 'stale' };
	try {
		const legacy = await deps.fetchHistory(shop, sku);
		if (!isActive()) return { status: 'stale' };
		if (legacy) return { status: 'found', card: cardFromLegacy(legacy) };
	} catch (e) {
		const reason = e instanceof Error ? e.message : String(e);
		return { status: 'unavailable', reason: catalogReason ?? reason };
	}
	if (!isActive()) return { status: 'stale' };
	if (catalogReason) return { status: 'unavailable', reason: catalogReason };
	const snap = deps.snapshot(`${shop}:${sku}`);
	if (snap) return { status: 'found', card: cardFromFavorites(snap) };
	return { status: 'missing' };
}

/* ================= View model цены ================= */

export interface PriceViewInput {
	/** Текущая цена продажи. */
	price: number | null;
	/** База из catalog-v2 или старого среза; при позиции со скидкой приоритет у базы витрины. */
	basePrice: number | null;
	/** Дней накопленной истории; null — истории нет. */
	coverageDays: number | null;
	/** Дата начала наблюдений (первая точка). */
	firstSeen?: string | null;
	/** Дата последнего наблюдения из catalog-v2. */
	lastSeen?: string | null;
	/** Позиция доступна для покупки (in_stock не false). */
	available: boolean;
	/** Позиция со скидкой витрины — тогда входы и вердикт как на витрине. */
	deal: Deal | null;
}

export type PriceView = {
	/** deal — скидка витрины; flat/below/above — сравнение с обычной ценой;
	 * thin-history — истории мало; no-base — база неизвестна; delisted — выбыл. */
	kind: 'deal' | 'flat' | 'below' | 'above' | 'thin-history' | 'no-base' | 'delisted';
	/** Подпись состояния цены. */
	label: string;
	/** Совет покупателю. */
	hint: string;
	/** Вердикт ИС — только для позиций со скидкой (verdictOf, как на витрине). */
	verdict: Verdict | null;
	price: number | null;
	/** База сравнения; null — неизвестна, тогда без процента экономии. */
	basePrice: number | null;
	/** Отклонение в тенге: база − цена; null — база неизвестна. */
	deviation: number | null;
	/** Экономия в процентах от базы; null — экономии нет или база неизвестна. */
	percent: number | null;
	/** Дата начала наблюдений. */
	firstSeen: string | null;
	/** Дата последнего наблюдения (выбывшие позиции). */
	lastSeen: string | null;
};

/**
 * Общий view model цены: одна база и один вывод для витрины и карточки каталога.
 * Для позиции со скидкой — те же входные данные и `verdictOf`, что на витрине.
 * Для позиции без акции — текущая цена, база и отклонение в тенге; цена при базе —
 * «На уровне обычной цены», короткая история — «Пока мало истории» с датой начала
 * наблюдений, неизвестная база — без процента экономии, выбытие — дата последнего
 * наблюдения и без предложения покупки.
 */
export function priceViewOf(input: PriceViewInput): PriceView {
	const price = input.price;
	const firstSeen = input.firstSeen ?? null;
	const lastSeen = input.lastSeen ?? null;
	if (input.deal) {
		const verdict = verdictOf(input.deal);
		const base = input.deal.base_price ?? input.basePrice ?? null;
		const deviation = base != null && price != null ? base - price : null;
		const percent = base != null && deviation != null && deviation > 0 ? (deviation / base) * 100 : null;
		return {
			kind: 'deal', label: verdict.label, hint: verdict.hint, verdict,
			price, basePrice: base, deviation, percent, firstSeen, lastSeen
		};
	}
	if (!input.available) {
		return {
			kind: 'delisted',
			label: 'Нет в продаже',
			hint: 'Позиция недоступна для покупки; показана последняя известная цена.',
			verdict: null, price, basePrice: null, deviation: null, percent: null, firstSeen, lastSeen
		};
	}
	if (input.coverageDays == null || input.coverageDays < MIN_COVERAGE_DAYS) {
		return {
			kind: 'thin-history',
			label: 'Пока мало истории',
			hint: 'Сравнение с обычной ценой появится по мере накопления истории.',
			verdict: null, price, basePrice: null, deviation: null, percent: null, firstSeen, lastSeen
		};
	}
	if (input.basePrice == null || price == null) {
		return {
			kind: 'no-base',
			label: 'Обычная цена неизвестна',
			hint: 'Сравнение с обычной ценой появится, когда накопится история.',
			verdict: null, price, basePrice: null, deviation: null, percent: null, firstSeen, lastSeen
		};
	}
	const deviation = input.basePrice - price;
	if (deviation === 0) {
		return {
			kind: 'flat',
			label: 'На уровне обычной цены',
			hint: 'Текущая цена совпадает с обычной — скидки сейчас нет.',
			verdict: null, price, basePrice: input.basePrice, deviation, percent: 0, firstSeen, lastSeen
		};
	}
	if (deviation > 0) {
		return {
			kind: 'below',
			label: 'Ниже обычной цены',
			hint: `Дешевле обычной на ${formatPrice(deviation)}.`,
			verdict: null, price, basePrice: input.basePrice, deviation, percent: (deviation / input.basePrice) * 100, firstSeen, lastSeen
		};
	}
	return {
		kind: 'above',
		label: 'Выше обычной цены',
		hint: `Дороже обычной на ${formatPrice(-deviation)}.`,
		verdict: null, price, basePrice: input.basePrice, deviation, percent: null, firstSeen, lastSeen
	};
}

/** Возврат со страницы товара: только явные пути приложения под base (`/`, `/deals`,
 * `/search`). Внешняя ссылка и протокол-относительная `//host` ведут к безопасному
 * каталогу — на `${base}/deals`. */
export function itemBackHref(from: string | null | undefined, base: string, origin: string): string {
	const fallback = `${base}/deals`;
	if (!from?.startsWith(`${base}/`)) return fallback;
	try {
		const target = new URL(from, origin);
		const allowed = [`${base}/`, `${base}/deals`, `${base}/search`];
		return target.origin === origin && allowed.includes(target.pathname)
			? target.pathname + target.search
			: fallback;
	} catch {
		return fallback;
	}
}

/* ================= Версионирование сторон legacy-истории ================= */

export type HistorySide = 'cloud' | 'local';

/**
 * Стороны legacy-среза истории: какая сторона какой версией latest **фактически**
 * загружена. Версия обновляется только после успешного fetch — сбой оставляет
 * предыдущее состояние, и следующий вызов повторяет попытку; 404 (fetch → null) —
 * валидная «пустая» версия. Запоздавший ответ не замещает данные более новой версии.
 */
export class SideVersions<T> {
	private files: Record<HistorySide, T | null> = { cloud: null, local: null };
	/** Версия, под которой файл фактически загружен; null — сторона ещё не загружалась. */
	private loaded: Record<HistorySide, string | null> = { cloud: null, local: null };
	/** Последняя запрошенная версия стороны — защита от запоздавших ответов. */
	private wanted: Record<HistorySide, string> = { cloud: '', local: '' };

	get(side: HistorySide): T | null {
		return this.files[side];
	}

	hasAny(): boolean {
		return !!(this.files.cloud || this.files.local);
	}

	/** Скачивает сторону, если её версия ещё не загружена. */
	async load(side: HistorySide, version: string, fetch: () => Promise<T | null>): Promise<void> {
		if (this.loaded[side] === version) return;
		this.wanted[side] = version;
		const file = await fetch();
		if (this.wanted[side] !== version) return;
		this.files[side] = file;
		this.loaded[side] = version;
	}
}
