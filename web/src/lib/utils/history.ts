import type { PricePoint } from '../types';

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
