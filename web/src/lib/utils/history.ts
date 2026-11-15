import type { PricePoint, Product } from '../types';

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
