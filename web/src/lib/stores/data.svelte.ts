import { base } from '$app/paths';
import type { DashboardData, Product, PricePoint, ProductHistory } from '$lib/types';

/** Пустой срез: панель до первого опубликованного обхода. */
const EMPTY: DashboardData = {
	updated_at: new Date(0).toISOString(),
	deals: [],
	shops: [],
	stats: { total_products: 0, total_deals: 0, avg_discount: 0 }
};

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
		try {
			// Кэш-бастер: браузер иначе отдаёт latest.json из кэша после деплоя.
			const res = await fetch(`${base}/data/latest.json?t=${Date.now()}`);
			// 404 — срез ещё не публиковался (первый обход не прошёл): это не
			// сбой панели, а пустое состояние.
			if (res.status === 404) {
				this.data = EMPTY;
				this.error = null;
				return;
			}
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			this.data = (await res.json()) as DashboardData;
			this.updatedAt = new Date(this.data.updated_at);
			this.error = null;
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
	history: Record<string, { points: PricePoint[]; min: number; median: number }>;
}

let historyCache: HistoryFile | null = null;
let historyPending: Promise<HistoryFile | null> | null = null;

async function loadHistoryFile(): Promise<HistoryFile | null> {
	if (historyCache) return historyCache;
	if (!historyPending) {
		historyPending = (async () => {
			try {
				const res = await fetch(`${base}/data/history.json?t=${Date.now()}`);
				if (!res.ok) return null;
				historyCache = (await res.json()) as HistoryFile;
				return historyCache;
			} catch {
				return null;
			} finally {
				historyPending = null;
			}
		})();
	}
	return historyPending;
}

/** История цен одного товара: позиция — из текущего среза, точки — из history.json. */
export async function fetchHistory(shop: string, sku: string): Promise<ProductHistory | null> {
	const snapshot = await loadHistoryFile();
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
		stats: {
			min_90d: row.min,
			median_30d: row.median,
			days_at_current: row.points.length
		}
	};
}
