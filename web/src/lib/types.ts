export interface Product {
	shop: string;
	sku: string;
	title: string;
	price: number;
	old_price?: number;
	url: string;
	brand?: string;
	category?: string;
	group?: string;
	in_stock: boolean;
	discount_pct?: number;
}

export interface ShopStatus {
	name: string;
	label: string;
	last_crawl: string;
	item_count: number;
	status: 'ok' | 'warning' | 'error';
	error?: string;
}

export interface Deal {
	product: Product;
	signal: 'deal' | 'drop' | 'low' | 'target' | 'restock';
	drop_pct?: number;
	base_price?: number;
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
	old_price?: number;
}

export interface ProductHistory {
	product: Product;
	history: PricePoint[];
	stats: {
		min_90d: number;
		median_30d: number;
		days_at_current: number;
	};
}
