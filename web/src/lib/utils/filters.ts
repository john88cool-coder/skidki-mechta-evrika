/** Дополнительные фильтры каталога — те, что спрятаны под кнопкой «Фильтры». */
export interface ExtraFilters {
	shop: string;
	group: string;
	brand: string;
	minPct: number;
	priceMax: string;
	inStockOnly: boolean;
	favOnly: boolean;
}

/** Сколько дополнительных фильтров включено: число на кнопке «Фильтры». */
export function countExtraFilters(f: ExtraFilters): number {
	return [
		f.shop !== 'all',
		f.group !== 'all',
		f.brand !== 'all',
		f.minPct > 0,
		f.priceMax !== 'all',
		f.inStockOnly,
		f.favOnly
	].filter(Boolean).length;
}
