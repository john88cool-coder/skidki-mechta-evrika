<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import { groupLabel, formatPrice } from '$lib/utils/format';
	import { RefreshCw } from '@lucide/svelte';

	// Сводка по магазину: сколько скидок, средняя глубина, самый глубокий товар.
	let perShop = $derived(
		dashboard.shops.map((shop) => {
			const deals = dashboard.deals.filter((d) => d.product.shop === shop.name);
			const avg = deals.length
				? deals.reduce((sum, d) => sum + (d.drop_pct ?? 0), 0) / deals.length
				: 0;
			const best = deals.reduce<(typeof deals)[number] | null>(
				(acc, d) => (!acc || (d.drop_pct ?? 0) > (acc.drop_pct ?? 0) ? d : acc),
				null
			);
			return { shop, deals: deals.length, avg, best };
		})
	);
</script>

<svelte:head>
	<title>Магазины — skidki</title>
</svelte:head>

<div class="mb-5 flex items-center justify-between">
	<h1 class="text-xl font-bold text-slate-100">Магазины</h1>
	<button
		onclick={() => dashboard.refresh()}
		class="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200"
	>
		<RefreshCw class="h-4 w-4 {dashboard.loading ? 'animate-spin' : ''}" /> Обновить
	</button>
</div>

<div class="space-y-4">
	{#each perShop as row (row.shop.name)}
		<div class="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
			<ShopStatusCard shop={row.shop} />

			<div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
				<div class="rounded-lg bg-slate-800/40 px-3 py-2">
					<p class="text-xs text-slate-500">Скидок в топе</p>
					<p class="font-semibold text-amber-400">{row.deals}</p>
				</div>
				<div class="rounded-lg bg-slate-800/40 px-3 py-2">
					<p class="text-xs text-slate-500">Средняя скидка</p>
					<p class="font-semibold text-slate-200">
						{row.deals ? `−${row.avg.toFixed(1)}%` : '—'}
					</p>
				</div>
				<div class="col-span-2 rounded-lg bg-slate-800/40 px-3 py-2 sm:col-span-1">
					<p class="text-xs text-slate-500">Глубочайшая находка</p>
					{#if row.best}
						<a
							href={row.best.product.url}
							target="_blank"
							rel="noopener"
							class="truncate font-semibold text-slate-200 hover:text-amber-400"
							title={row.best.product.title}
						>
							−{Math.round(row.best.drop_pct ?? 0)}% · {formatPrice(row.best.product.price)}
						</a>
					{:else}
						<p class="font-semibold text-slate-500">—</p>
					{/if}
				</div>
			</div>

			{#if row.shop.status !== 'ok' && row.shop.error}
				<p class="mt-2 truncate text-xs text-red-400" title={row.shop.error}>
					⚠ {row.shop.error}
				</p>
			{/if}
		</div>
	{/each}
</div>

<!-- Скидки по группам уведомлений -->
<section class="mt-8">
	<h2 class="mb-4 text-lg font-bold text-slate-100">Скидки по группам</h2>
	<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
		{#each Object.entries(
			dashboard.deals.reduce<Record<string, number>>((acc, d) => {
				const key = d.product.group ?? 'other';
				acc[key] = (acc[key] ?? 0) + 1;
				return acc;
			}, {})
		) as [key, count] (key)}
			<div class="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3">
				<span class="text-sm text-slate-300">{groupLabel(key)}</span>
				<span class="font-semibold text-amber-400">{count}</span>
			</div>
		{:else}
			<p class="text-sm text-slate-500">Нет данных</p>
		{/each}
	</div>
</section>