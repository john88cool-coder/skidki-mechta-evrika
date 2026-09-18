<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard, fetchHistory } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice, shopLabel, groupLabel } from '$lib/utils/format';
	import type { ProductHistory } from '$lib/types';
	import { Package, Tag, TrendingDown, ArrowRight } from '@lucide/svelte';

	let featured = $state<ProductHistory | null>(null);
	let featuredKey = $state('');
	const topCount = 8;

	// График на главной — история самого глубокого товара: панель показывает
	// реальные данные, а не демо-заготовку.
	$effect(() => {
		const best = dashboard.deals[0];
		if (!best) return;
		const key = `${best.product.shop}:${best.product.sku}`;
		if (key === featuredKey) return;
		featuredKey = key;
		fetchHistory(best.product.shop, best.product.sku).then((data) => {
			featured = data;
		});
	});

	let byGroup = $derived.by(() => {
		const acc = new Map<string, { count: number; total: number }>();
		for (const deal of dashboard.deals) {
			const key = deal.product.group ?? 'other';
			const row = acc.get(key) ?? { count: 0, total: 0 };
			row.count += 1;
			row.total += deal.drop_pct ?? 0;
			acc.set(key, row);
		}
		return [...acc.entries()]
			.map(([key, row]) => ({ key, count: row.count, avg: row.total / row.count }))
			.sort((a, b) => b.count - a.count);
	});
</script>

<svelte:head>
	<title>skidki — мониторинг скидок</title>
</svelte:head>

{#if dashboard.loading && !dashboard.data}
	<div class="flex h-96 items-center justify-center">
		<span class="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-slate-700 border-t-amber-500"></span>
	</div>
{:else}
	<!-- KPI -->
	<section class="mb-8 grid gap-4 sm:grid-cols-3">
		<div class="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
			<div class="flex items-center gap-2 text-sm text-slate-400">
				<Package class="h-4 w-4" /> Позиций в базе
			</div>
			<p class="mt-2 text-2xl font-bold text-slate-100">
				{dashboard.stats.total_products.toLocaleString('ru-RU')}
			</p>
		</div>
		<div class="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
			<div class="flex items-center gap-2 text-sm text-slate-400">
				<Tag class="h-4 w-4" /> Скидок сейчас
			</div>
			<p class="mt-2 text-2xl font-bold text-amber-400">{dashboard.stats.total_deals}</p>
		</div>
		<div class="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
			<div class="flex items-center gap-2 text-sm text-slate-400">
				<TrendingDown class="h-4 w-4" /> Средняя скидка
			</div>
			<p class="mt-2 text-2xl font-bold text-slate-100">
				−{dashboard.stats.avg_discount.toFixed(1)}%
			</p>
		</div>
	</section>

	<!-- Топ скидки -->
	<section class="mb-8">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-xl font-bold text-slate-100">🔥 Топ скидки</h2>
			<a
				href="{base}/deals"
				class="flex items-center gap-1 text-sm text-amber-400 hover:text-amber-300"
			>
				Все {dashboard.deals.length} <ArrowRight class="h-4 w-4" />
			</a>
		</div>

		<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
			{#each dashboard.deals.slice(0, topCount) as deal, i (deal.product.shop + deal.product.sku)}
				<DealCard {deal} rank={i + 1} />
			{:else}
				<div class="col-span-full rounded-xl bg-slate-800/50 p-8 text-center text-slate-400">
					Пока нет скидок. Первый обход скоро появится.
				</div>
			{/each}
		</div>
	</section>

	<!-- График и группы -->
	<div class="mb-8 grid gap-6 lg:grid-cols-2">
		<section class="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
			<h3 class="mb-1 font-semibold text-slate-200">📉 Динамика цены</h3>
			{#if featured}
				<p class="mb-4 truncate text-xs text-slate-500" title={featured.product.title}>
					{shopLabel(featured.product.shop)} · {featured.product.title}
				</p>
				<PriceChart
					data={featured.history}
					height={190}
					labelFormatter={(d) => (d.length >= 10 ? d.slice(5) : d)}
				/>
				<div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
					<div>
						<p class="text-slate-500">минимум</p>
						<p class="font-semibold text-emerald-400">{formatPrice(featured.stats.min_90d)}</p>
					</div>
					<div>
						<p class="text-slate-500">медиана</p>
						<p class="font-semibold text-slate-300">{formatPrice(featured.stats.median_30d)}</p>
					</div>
					<div>
						<p class="text-slate-500">сейчас</p>
						<p class="font-semibold text-amber-400">{formatPrice(featured.product.price)}</p>
					</div>
				</div>
			{:else}
				<div class="flex h-[220px] items-center justify-center text-sm text-slate-500">
					История появится после нескольких обходов
				</div>
			{/if}
		</section>

		<section class="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
			<h3 class="mb-4 font-semibold text-slate-200">📊 Скидки по группам</h3>
			{#if byGroup.length}
				<div class="space-y-3">
					{#each byGroup as row (row.key)}
						<div class="flex items-center justify-between gap-4">
							<span class="truncate text-sm text-slate-300">{groupLabel(row.key)}</span>
							<div class="flex items-center gap-3">
								<div class="h-2 w-24 overflow-hidden rounded-full bg-slate-700">
									<div
										class="h-full rounded-full bg-amber-500"
										style="width: {Math.min(row.avg * 1.5, 100)}%"
									></div>
								</div>
								<span class="w-12 text-right text-sm font-medium text-amber-400">
									−{row.avg.toFixed(0)}%
								</span>
								<span class="w-8 text-right text-sm text-slate-500">{row.count}</span>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-slate-500">Нет данных</p>
			{/if}
		</section>
	</div>

	<!-- Магазины -->
	<section>
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-xl font-bold text-slate-100">Магазины</h2>
			<a
				href="{base}/shops"
				class="flex items-center gap-1 text-sm text-amber-400 hover:text-amber-300"
			>
				Подробнее <ArrowRight class="h-4 w-4" />
			</a>
		</div>
		<div class="space-y-2">
			{#each dashboard.shops as shop (shop.name)}
				<ShopStatusCard {shop} />
			{:else}
				<div class="rounded-xl bg-slate-800/50 p-8 text-center text-slate-400">
					Данных обходов пока нет — панель наполнится после первого запуска.
				</div>
			{/each}
		</div>
	</section>
{/if}
