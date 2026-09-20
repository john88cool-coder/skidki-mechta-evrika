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
}

export interface ShopStatus {
	name: string;
	label: string;
	last_crawl: string;
	item_count: number;
	status: 'ok' | 'warning' | 'error';
	error?: string | null;
}

export interface Deal {
	product: Product;
	signal: 'deal' | 'drop' | 'low' | 'target' | 'restock';
	drop_pct?: number | null;
	base_price?: number | null;
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

