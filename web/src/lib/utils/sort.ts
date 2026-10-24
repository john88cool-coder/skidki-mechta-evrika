import type { Deal } from '../types';
import { byNovelty } from './novelty.ts';
import { realRank } from './verdict.ts';

/** Ключи сортировки списков товаров. Одни и те же на всех страницах каталога. */
export type SortKey = 'real' | 'new' | 'claimed' | 'price' | 'price_desc' | 'title';

export const SORT_LABELS: Record<SortKey, string> = {
	real: 'Реальная выгода',
	new: 'Сначала новинки',
	claimed: 'Скидка на ценнике',
	price: 'Сначала дешевле',
	price_desc: 'Сначала дороже',
	title: 'По названию'
};

/**
 * Компаратор по ключу сортировки. Общий для страниц списков (/deals,
 * /favorites), чтобы порядок товаров не расходился между страницами.
 */
export function bySortKey(key: SortKey): (a: Deal, b: Deal) => number {
	return (a, b) => {
		switch (key) {
			case 'new':
				return byNovelty(a, b);
			case 'price':
				return a.product.price - b.product.price;
			case 'price_desc':
				return b.product.price - a.product.price;
			case 'title':
				return a.product.title.localeCompare(b.product.title, 'ru');
			case 'claimed':
				return (b.drop_pct ?? 0) - (a.drop_pct ?? 0);
			default:
				return realRank(b) - realRank(a);
		}
	};
}
