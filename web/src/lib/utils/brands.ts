import type { Deal } from '../types';

/** Ключ бренда без учёта регистра и пробелов: «BORK», «Bork» и «Bork » — один бренд. */
export function brandKey(brand: string | null | undefined): string {
	return (brand ?? '').trim().toLocaleLowerCase('ru');
}

export interface BrandOption {
	/** Значение фильтра и параметра ссылки. */
	key: string;
	/** Самое частое написание — его и показываем. */
	label: string;
	count: number;
}

/** Список брендов для фильтра: дубли по регистру и пробелам склеены. */
export function brandOptions(deals: Pick<Deal, 'product'>[]): BrandOption[] {
	const groups = new Map<string, Map<string, number>>();
	for (const d of deals) {
		const key = brandKey(d.product.brand);
		if (!key) continue;
		const spelling = d.product.brand!.trim();
		const variants = groups.get(key) ?? new Map<string, number>();
		variants.set(spelling, (variants.get(spelling) ?? 0) + 1);
		groups.set(key, variants);
	}
	return [...groups.entries()]
		.map(([key, variants]) => {
			const ranked = [...variants.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ru'));
			return { key, label: ranked[0][0], count: ranked.reduce((sum, [, n]) => sum + n, 0) };
		})
		.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'ru'));
}
