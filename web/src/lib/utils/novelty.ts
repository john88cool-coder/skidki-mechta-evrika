import type { Deal } from '../types';

/**
 * Новизна позиции: когда товар впервые появился в мониторинге.
 *
 * В срезе это `product.first_seen` (минимум по отрезкам истории). Позиции без
 * даты (старый срез в кэше браузера) считаются самыми старыми — падают в конец.
 */
export function firstSeenMs(deal: Pick<Deal, 'product'>): number {
	const raw = deal.product.first_seen;
	if (!raw) return 0;
	const ms = Date.parse(raw);
	return Number.isNaN(ms) ? 0 : ms;
}

/** Компаратор «сначала новинки»: новые позиции выше, старые и без даты — ниже. */
export function byNovelty(
	a: Pick<Deal, 'product'>,
	b: Pick<Deal, 'product'>
): number {
	return firstSeenMs(b) - firstSeenMs(a);
}
