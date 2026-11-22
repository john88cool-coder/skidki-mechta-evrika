import { base } from '$app/paths';
import type { DashboardData, Product, PricePoint, ProductHistory } from '$lib/types';
import { mergeSnapshots, withFreshness, freshnessOf } from '$lib/utils/merge';
import {
	buildFallbackProduct,
	computeDaysAtCurrent,
	loadItemCard,
	type ItemLoad
} from '$lib/utils/history';
import { getSnapshot } from '$lib/utils/snapshots';
import { catalog } from '$lib/stores/catalog.svelte';

/** Пустой срез: панель до первого опубликованного обхода. */
const EMPTY: DashboardData = {
	updated_at: new Date(0).toISOString(),
	deals: [],
	shops: [],
	stats: { total_products: 0, total_deals: 0, avg_discount: 0 }
};

/** Срез может отсутствовать (404) — это не ошибка, а «ещё не публиковался». */
async function fetchJson<T>(path: string): Promise<T | null> {
	const res = await fetch(`${base}/data/${path}?t=${Date.now()}`);
	if (res.status === 404) return null;
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	return (await res.json()) as T;
}

/**
 * Хранилище данных панели на рунах Svelte 5.
 *
 * Один общий объект-класс вместо writable-сторов: автообновление раз в 5 минут
 * переписывает поля целиком, а страницы читают их реактивно.
 */
class DashboardStore {
	data = $state<DashboardData | null>(null);
	loading = $state(true);
	error = $state<string | null>(null);
	updatedAt = $state<Date | null>(null);
	/** Версия каждой стороны — свой latest; updated_at дашборда версией магазина не является. */
	cloudVersion = $state('');
	localVersion = $state('');

	get deals() {
		return this.data?.deals ?? [];
	}

	get shops() {
		return this.data?.shops ?? [];
	}

	get stats() {
		return this.data?.stats ?? { total_products: 0, total_deals: 0, avg_discount: 0 };
	}

	/** Свежесть — по самому старому магазину (см. freshnessOf). */
	get freshness() {
		return freshnessOf(this.shops);
	}

	async refresh(): Promise<void> {
		if (this.loading && this.data) return;
		this.loading = true;
		try {
			// Кэш-бастер в fetchJson: браузер иначе отдаёт срез из кэша после деплоя.
			const [cloud, local] = await Promise.all([
				fetchJson<DashboardData>('latest.json'),
				fetchJson<DashboardData>('local/latest.json').catch(() => null)
			]);
			const merged = mergeSnapshots(cloud, local);
			// Ни одного среза — первый обход ещё не публиковался: пустое состояние.
			if (!merged) {
				this.data = EMPTY;
				this.updatedAt = null;
				this.error = null;
				return;
			}
			this.data = withFreshness(merged);
			this.updatedAt = new Date(this.data.updated_at);
			this.error = null;
			this.cloudVersion = cloud?.updated_at ?? '';
			this.localVersion = local?.updated_at ?? '';
			// Legacy-срез истории загружают потребители (карточки, страницы товара),
			// а не refresh: витрина без карточек не тянет историю.
		} catch (e) {
			this.error = e instanceof Error ? e.message : String(e);
		} finally {
			this.loading = false;
		}
	}
}

export const dashboard = new DashboardStore();

let timer: ReturnType<typeof setInterval> | undefined;
let onVisibility: (() => void) | undefined;
let lastRefreshTick = 0;

/** Автообновление раз в 5 минут только для активной вкладки; возвращает функцию остановки. */
export function startAutoRefresh(intervalMs = 300_000): () => void {
	stopAutoRefresh();
	lastRefreshTick = Date.now();
	timer = setInterval(() => {
		if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
		lastRefreshTick = Date.now();
		void dashboard.refresh();
	}, intervalMs);
	if (typeof document !== 'undefined') {
		onVisibility = () => {
			if (document.visibilityState === 'visible' && Date.now() - lastRefreshTick >= intervalMs) {
				lastRefreshTick = Date.now();
				void dashboard.refresh();
			}
		};
		document.addEventListener('visibilitychange', onVisibility);
	}
	return stopAutoRefresh;
}

export function stopAutoRefresh(): void {
	if (timer) clearInterval(timer);
	timer = undefined;
	if (onVisibility && typeof document !== 'undefined') {
		document.removeEventListener('visibilitychange', onVisibility);
	}
	onVisibility = undefined;
}

/** Срез истории: один файл на все товары — отдельный JSON на позицию давал
 * ~10 тыс. файлов на каждый обход (дорого для git и gh-pages). */
interface HistoryFile {
	updated_at: string;
	history: Record<
		string,
		{ points: PricePoint[]; recent_points?: PricePoint[]; min: number; median: number; days_at_current?: number }
	>;
}

/** One request shared by all cards, refreshed when the published snapshot changes.
 * Каждая сторона версионирована своим latest: смена локального среза не
 * перезагружает облачную историю и наоборот. */
class PriceHistoryStore {
	data = $state<HistoryFile | null>(null);
	loading = $state(false);
	error = $state(false);
	private versions: { cloud: string; local: string } = { cloud: '', local: '' };
	private files: { cloud: HistoryFile | null; local: HistoryFile | null } = { cloud: null, local: null };
	private pending: Promise<HistoryFile | null> | null = null;

	load(
		cloudVersion = dashboard.cloudVersion,
		localVersion = dashboard.localVersion
	): Promise<HistoryFile | null> {
		const key = `${cloudVersion}|${localVersion}`;
		const current = `${this.versions.cloud}|${this.versions.local}`;
		if (key === current) {
			if (this.pending) return this.pending;
			if (this.data) return Promise.resolve(this.data);
		}
		this.versions = { cloud: cloudVersion, local: localVersion };
		this.loading = true;
		this.error = false;
		const request = (async () => {
			try {
				await Promise.all([this.loadSide('cloud', cloudVersion), this.loadSide('local', localVersion)]);
				if (!this.files.cloud && !this.files.local) throw new Error('история не опубликована');
				const snapshot: HistoryFile = {
					updated_at: this.files.cloud?.updated_at ?? this.files.local!.updated_at,
					history: { ...(this.files.cloud?.history ?? {}), ...(this.files.local?.history ?? {}) }
				};
				if (this.versions.cloud === cloudVersion && this.versions.local === localVersion) {
					this.data = snapshot;
				}
				return snapshot;
			} catch {
				if (this.versions.cloud === cloudVersion && this.versions.local === localVersion) this.error = true;
				return null;
			} finally {
				if (this.versions.cloud === cloudVersion && this.versions.local === localVersion) {
					this.pending = null;
					this.loading = false;
				}
			}
		})();
		this.pending = request;
		return request;
	}

	/** Сторона перезагружается только при смене своего latest; 404 — тоже валидная версия («пусто»). */
	private async loadSide(side: 'cloud' | 'local', version: string): Promise<void> {
		if (this.files[side] && this.versions[side] === version) return;
		const file =
			side === 'cloud'
				? await fetchJson<HistoryFile>('history.json')
				: await fetchJson<HistoryFile>('local/history.json').catch(() => null);
		// Запоздавший ответ не замещает данные более новой версии стороны.
		if (this.versions[side] !== version) return;
		this.files[side] = file;
	}
}

export const priceHistory = new PriceHistoryStore();

/** История цен одного товара: позиция — из текущего среза, точки — из history.json.
 * Витрина не знает позицию — карточка catalog-v2: только её индекс и история,
 * без полноразмерных историй остальных магазинов. */
export async function fetchHistory(shop: string, sku: string): Promise<ProductHistory | null> {
	const snapshot = await priceHistory.load();
	const row = snapshot?.history[`${shop}:${sku}`];
	if (row?.points?.length) {
		const current = dashboard.deals.find(
			(deal) => deal.product.shop === shop && deal.product.sku === sku
		)?.product;

		const product: Product =
			current ?? buildFallbackProduct(shop, sku, row.points, getSnapshot(`${shop}:${sku}`));

		return {
			product,
			history: row.points,
			recent: row.recent_points ?? row.points,
			stats: {
				min_90d: row.min,
				median_30d: row.median,
				days_at_current: row.days_at_current ?? computeDaysAtCurrent(row.points)
			}
		};
	}

	const catalogRow = (await catalog.loadIndex(shop))?.rows.find((r) => r.product.sku === sku);
	if (!catalogRow) return null;
	const history = await catalog.loadHistory(shop, sku);
	if (!history?.points?.length) return null;
	return {
		product: catalogRow.product,
		history: history.points,
		recent: history.recent_points ?? history.points,
		stats: {
			min_90d: history.min ?? 0,
			median_30d: history.median ?? 0,
			days_at_current: history.days_at_current
		}
	};
}

/** Товар по (shop, sku): catalog-v2 → старый срез (существующий путь через
 * fetchHistory) → сохранённая копия избранного. Результаты различимы:
 * found / missing / unavailable (сбой сети — товар можно запросить повторно).
 * isActive отбрасывает устаревший ответ при быстром переходе A → B. */
export function loadCatalogItem(shop: string, sku: string, isActive: () => boolean = () => true): Promise<ItemLoad> {
	return loadItemCard({ loader: catalog, fetchHistory, snapshot: (id) => getSnapshot(id) }, shop, sku, isActive);
}
