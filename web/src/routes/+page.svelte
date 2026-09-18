<script lang="ts">
	import { deals, shops, topDeals, loading } from '$lib/stores/data';
	import DealCard from '$lib/components/DealCard.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice } from '$lib/utils/format';

	// Демо-данные для графика (пока нет реальной истории)
	const chartData = [
		{ date: '12 сен', price: 189990 },
		{ date: '13 сен', price: 189990 },
		{ date: '14 сен', price: 179990 },
		{ date: '15 сен', price: 179990 },
		{ date: '16 сен', price: 169990 },
		{ date: '17 сен', price: 159990 },
		{ date: '18 сен', price: 149990 },
	];
</script>

<svelte:head>
	<title>skidki — мониторинг скидок</title>
</svelte:head>

{#if $loading}
	<div class="flex h-96 items-center justify-center">
		<span class="loading loading-spinner loading-lg text-amber-500"></span>
	</div>
{:else}
	<!-- Топ скидки -->
	<section class="mb-8">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-xl font-bold text-slate-100">🔥 Топ скидки</h2>
			<a href="/deals" class="text-sm text-amber-400 hover:text-amber-300">
				Все {$deals.length} →
			</a>
		</div>
		
		<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
			{#each $topDeals as deal, i}
				<DealCard {deal} rank={i + 1} />
			{:else}
				<div class="col-span-full rounded-xl bg-slate-800/50 p-8 text-center text-slate-400">
					Пока нет скидок. Первый обход скоро появится.
				</div>
			{/each}
		</div>
	</section>

	<!-- График и статистика -->
	<div class="mb-8 grid gap-6 lg:grid-cols-2">
		<section class="rounded-xl bg-slate-900/50 p-5 border border-slate-800">
			<h3 class="mb-4 font-semibold text-slate-200">📉 Пример: динамика цены</h3>
			<PriceChart data={chartData} height={180} />
			<p class="mt-2 text-xs text-slate-500">Galaxy Watch Ultra — падение за неделю</p>
		</section>

		<section class="rounded-xl bg-slate-900/50 p-5 border border-slate-800">
			<h3 class="mb-4 font-semibold text-slate-200">📊 По группам</h3>
			<div class="space-y-3">
				{#each [
					{ label: 'Смартфоны', pct: 12, count: 45 },
					{ label: 'Ноутбуки', pct: 8, count: 23 },
					{ label: 'ТВ', pct: 15, count: 31 },
					{ label: 'Для дома', pct: 5, count: 67 },
				] as row}
					<div class="flex items-center justify-between">
						<span class="text-slate-300">{row.label}</span>
						<div class="flex items-center gap-3">
							<div class="h-2 w-24 rounded-full bg-slate-700">
								<div 
									class="h-full rounded-full bg-amber-500" 
									style="width: {Math.min(row.pct * 5, 100)}%"
								></div>
							</div>
							<span class="text-sm font-medium text-amber-400 w-12">−{row.pct}%</span>
							<span class="text-sm text-slate-500 w-8">{row.count}</span>
						</div>
					</div>
				{/each}
			</div>
		</section>
	</div>

	<!-- Статус магазинов -->
	<section>
		<h2 class="mb-4 text-xl font-bold text-slate-100">Магазины</h2>
		<div class="space-y-2">
			{#each $shops as shop}
				<ShopStatusCard {shop} />
			{:else}
				<div class="rounded-xl bg-slate-800/50 p-8 text-center text-slate-400">
					Загрузка статуса магазинов...
				</div>
			{/each}
		</div>
	</section>
{/if}
