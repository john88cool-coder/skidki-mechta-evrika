export interface Product {
	shop: string;
	sku: string;
	title: string;
	price: number;
	old_price?: number | null;
	url: string;
	brand?: string | null;
	category?: string | null;
	group?: string | null;
	in_stock: boolean;
	discount_pct?: number | null;
	image?: string | null;
	mpn?: string | null;
	/** Когда позиция впервые появилась в мониторинге (для сортировки по новизне). */
	first_seen?: string | null;
	// scoring (опционально, бэкфилл)
	fair_discount?: number | null;
	value_score?: number | null;
	is_pick?: boolean | null;
	badges?: string[] | null;
	inflated_gap?: number | null;
	rating?: number | null;
	reviews_count?: number | null;
}

export interface ShopStatus {
	name: string;
	label: string;
	last_crawl: string | null;
	item_count: number;
	status: 'ok' | 'warning' | 'error';
	error?: string | null;
}

export interface Deal {
	product: Product;
	signal: 'deal' | 'drop' | 'low' | 'target' | 'restock';
	drop_pct?: number | null;
	base_price?: number | null;
	/** Накрутка: до этой цены товар поднимали перед скидкой (иначе null). */
	pump_price?: number | null;
	fair_discount?: number | null;
	value_score?: number | null;
	is_pick?: boolean | null;
	badges?: string[] | null;
	inflated_gap?: number | null;
}

export interface DashboardData {
	updated_at: string;
	deals: Deal[];
	shops: ShopStatus[];
	stats: {
		total_products: number;
		total_deals: number;
		avg_discount: number;
	};
}

export interface PricePoint {
	date: string;
	price: number;
	old_price?: number | null;
}

export interface ProductHistory {
	product: Product;
	history: PricePoint[];
	recent?: PricePoint[];
	stats: {
		min_90d: number;
		median_30d: number;
		days_at_current: number;
	};
}

/** catalog-v2 (задача 2): одна строка индекса магазина — товар и его оценки. */
export interface CatalogRow {
	product: Product;
	last_seen: string | null;
	base_price: number | null;
	fair_discount: number | null;
	pump_price: number | null;
	/** Точное совпадение модели; до задачи 6 всегда null. */
	exact_model: null;
}

export interface CatalogIndex {
	schema: number;
	shop: string;
	rows: CatalogRow[];
}

/** Запись манифеста: магазин без успешного обхода в `shops` отсутствует (absent ≠ пусто). */
export interface CatalogManifestEntry {
	last_crawl: string;
	count: number;
	index_sha256: string;
	history_sha256: string;
}

export interface CatalogManifest {
	schema: number;
	shops: Record<string, CatalogManifestEntry>;
}

/** catalog-v2: история одной позиции. Legacy-имён min_90d/median_30d в v2 нет. */
export interface HistoryRow {
	points: PricePoint[];
	recent_points: PricePoint[];
	min: number | null;
	median: number | null;
	days_at_current: number;
	/** ISO Z первого наблюдения в наличии из выборки отрезков файла; null — в наличии не наблюдали. */
	first_stocked?: string | null;
	/** Старые файлы до задачи «Стабильность»: числовое покрытие от момента их выпуска. */
	coverage_days?: number;
}

export interface CatalogHistoryFile {
	schema: number;
	shop: string;
	items: Record<string, HistoryRow>;
}

/** Сторона, чей источник данные использует для магазина (см. selectShopSources). */
export type ShopSource = 'cloud' | 'local';
