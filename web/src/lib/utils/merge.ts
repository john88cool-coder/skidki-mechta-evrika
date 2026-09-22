import type { DashboardData } from '../types';

function median(values: number[]): number {
	if (!values.length) return 0;
	const sorted = [...values].sort((a, b) => a - b);
	return sorted[Math.floor(sorted.length / 2)];
}

/**
 * Облачный срез + срез домашнего ПК (data/local/). mechta обходится только
 * с ПК: облачный срез её не знает и помечал «требует проверки». Из
 * локального среза берутся магазины, которые ПК реально обходил; их строки
 * и скидки заменяют облачные.
 */
export function mergeSnapshots(cloud: DashboardData | null, local: DashboardData | null): DashboardData | null {
	if (!local) return cloud;
	if (!cloud) return local;
	const localShops = new Set(local.shops.filter((s) => s.last_crawl).map((s) => s.name));
	if (!localShops.size) return cloud;
	const shops = cloud.shops.map((s) => (localShops.has(s.name) ? local.shops.find((l) => l.name === s.name)! : s));
	for (const s of local.shops) if (localShops.has(s.name) && !shops.some((x) => x.name === s.name)) shops.push(s);
	const suspicious = (d: DashboardData['deals'][number]) => (d.badges ?? []).includes('Рисованная?');
	const deals = [
		...cloud.deals.filter((d) => !localShops.has(d.product.shop)),
		...local.deals.filter((d) => localShops.has(d.product.shop))
	].sort((a, b) => Number(suspicious(a)) - Number(suspicious(b)) || (b.drop_pct ?? 0) - (a.drop_pct ?? 0));
	return {
		updated_at: cloud.updated_at > local.updated_at ? cloud.updated_at : local.updated_at,
		deals,
		shops,
		stats: {
			total_products: shops.reduce((sum, s) => sum + (s.item_count ?? 0), 0),
			total_deals: deals.length,
			avg_discount: median(deals.map((d) => d.drop_pct ?? 0))
		}
	};
}


/** Статус «актуально» считается при выгрузке и стареет вместе со срезом:
 * облачный срез 9-часовой давности всё ещё говорил «актуально». */
export function withFreshness(data: DashboardData, now = Date.now(), staleAfterMs = 6 * 3600_000): DashboardData {
	return {
		...data,
		shops: data.shops.map((s) =>
			s.status === 'ok' && s.last_crawl && now - new Date(s.last_crawl).getTime() > staleAfterMs
				? { ...s, status: 'warning' as const }
				: s
		)
	};
}
