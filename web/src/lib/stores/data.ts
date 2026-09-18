import { writable, derived } from 'svelte/store';
import type { DashboardData, Deal, ShopStatus } from '$lib/types';

export const dashboardData = writable<DashboardData | null>(null);
export const loading = writable(true);
export const lastUpdate = writable<Date | null>(null);

export const deals = derived(dashboardData, ($data) => $data?.deals ?? []);
export const shops = derived(dashboardData, ($data) => $data?.shops ?? []);

export const topDeals = derived(deals, ($deals) => 
	$deals.slice(0, 4)
);

export const hasNewDeals = writable(false);

export async function fetchDashboard() {
	loading.set(true);
	try {
		const res = await fetch('/data/latest.json');
		if (res.ok) {
			const data = await res.json();
			dashboardData.set(data);
			lastUpdate.set(new Date());
		}
	} catch (e) {
		console.error('Failed to fetch dashboard:', e);
	} finally {
		loading.set(false);
	}
}

// Автообновление каждые 30 секунд
let interval: ReturnType<typeof setInterval>;
export function startAutoRefresh() {
	interval = setInterval(fetchDashboard, 30000);
}

export function stopAutoRefresh() {
	clearInterval(interval);
}
