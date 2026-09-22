import { base } from '$app/paths';
import type { DashboardData, Product, PricePoint, ProductHistory } from '$lib/types';
import { mergeSnapshots } from '$lib/utils/merge';

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
 * Один общий объект-класс вместо writable-сторов: автообновление раз в 30 с
 * переписывает поля целиком, а страницы читают их реактивно.
 */
class DashboardStore {
	data = $state<DashboardData | null>(null);
	loading = $state(true);
	error = $state<string | null>(null);
	updatedAt = $state<Date | null>(null);

	get deals() {
		return this.data?.deals ?? [];
	}

	get shops() {
		return this.data?.shops ?? [];
	}

	get stats() {
		return this.data?.stats ?? { total_products: 0, total_deals: 0, avg_discount: 0 };
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
			this.data = merged;
			this.updatedAt = new Date(this.data.updated_at);
			this.error = null;
			void priceHistory.load(this.data.updated_at);
		} catch (e) {
			this.error = e instanceof Error ? e.message : String(e);
		} finally {
			this.loading = false;
		}
	}
}

export const dashboard = new DashboardStore();

let timer: ReturnType<typeof setInterval> | undefined;

/** Автообновление каждые 30 секунд; возвращает функцию остановки. */
export function startAutoRefresh(intervalMs = 30_000): () => void {
	stopAutoRefresh();
	timer = setInterval(() => dashboard.refresh(), intervalMs);
	return stopAutoRefresh;
}

export function stopAutoRefresh(): void {
	if (timer) clearInterval(timer);
	timer = undefined;
}

/** Срез истории: один файл на все товары — отдельный JSON на позицию давал
 * ~10 тыс. файлов на каждый обход (дорого для git и gh-pages). */
interface HistoryFile {
	updated_at: string;
	history: Record<string, { points: PricePoint[]; recent_points?: PricePoint[]; min: number; median: number }>;
}

/** One request shared by all cards, refreshed when the published snapshot changes. */
class PriceHistoryStore {
	data = $state<HistoryFile | null>(null);
	loading = $state(false);
	error = $state(false);
	private version = '';
	private pending: Promise<HistoryFile | null> | null = null;

	load(version = dashboard.data?.updated_at ?? ''): Promise<HistoryFile | null> {
		if (version === this.version) {
			if (this.pending) return this.pending;
			if (this.data) return Promise.resolve(this.data);
		}
		this.version = version;
		this.data = null;
		this.loading = true;
		this.error = false;
		const request = (async () => {
			try {
				const [cloud, local] = await Promise.all([
					fetchJson<HistoryFile>('history.json'),
					fetchJson<HistoryFile>('local/history.json').catch(() => null)
				]);
				if (!cloud && !local) throw new Error('история не опубликована');
				const snapshot: HistoryFile = {
					updated_at: cloud?.updated_at ?? local!.updated_at,
					history: { ...(cloud?.history ?? {}), ...(local?.history ?? {}) }
				};
				if (this.version === version) this.data = snapshot;
				return snapshot;
			} catch {
				if (this.version === version) this.error = true;
				return null;
			} finally {
				if (this.version === version) {
					this.pending = null;
					this.loading = false;
				}
			}
		})();
		this.pending = request;
		return request;
	}
}

export const priceHistory = new PriceHistoryStore();

/** История цен одного товара: позиция — из текущего среза, точки — из history.json. */
export async function fetchHistory(shop: string, sku: string): Promise<ProductHistory | null> {
	const snapshot = await priceHistory.load();
	const row = snapshot?.history[`${shop}:${sku}`];
	if (!row?.points?.length) return null;

	const current = dashboard.deals.find(
		(deal) => deal.product.shop === shop && deal.product.sku === sku
	)?.product;

	// Товара может не быть в текущем топе (скидка кончилась) — тогда берём
	// последнюю известную точку истории и открываем страницу без ссылки.
	const product: Product = current ?? {
		shop,
		sku,
		title: `${shop} · ${sku}`,
		price: row.points[row.points.length - 1].price,
		url: '#',
		in_stock: true
	};

	return {
		product,
		history: row.points,
		recent: row.recent_points ?? row.points,
		stats: {
			min_90d: row.min,
			median_30d: row.median,
			days_at_current: row.points.length
		}
	};
}
