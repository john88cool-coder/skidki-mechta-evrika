import type { Deal } from '../types';
import { isReal, verdictOf } from './verdict.ts';

/** Похожая цена: не дешевле вдвое и не дороже вдвое. */
const MAX_PRICE_RATIO = 2;

/**
 * «Похожие» на странице товара: та же группа и похожая цена.
 * Сначала — та же категория магазина, внутри — реальные снижения, затем ближайшие по цене.
 * Раньше к ноутбуку предлагались мониторы и клавиатура «того же бренда».
 */
export function relatedDeals(target: Deal, deals: Deal[], limit = 4): Deal[] {
	const price = target.product.price;
	const group = target.product.group ?? 'other';
	const category = target.product.category ?? null;
	if (!(price > 0)) return [];
	return deals
		.filter((d) => !(d.product.shop === target.product.shop && d.product.sku === target.product.sku))
		.filter((d) => (d.product.group ?? 'other') === group && d.product.price > 0)
		.map((d) => ({
			d,
			sameCategory: category !== null && d.product.category === category,
			real: isReal(verdictOf(d).kind),
			distance: Math.abs(Math.log(d.product.price / price))
		}))
		.filter((row) => row.distance <= Math.log(MAX_PRICE_RATIO))
		.sort(
			(a, b) =>
				Number(b.sameCategory) - Number(a.sameCategory) ||
				Number(b.real) - Number(a.real) ||
				a.distance - b.distance
		)
		.slice(0, limit)
		.map((row) => row.d);
}
