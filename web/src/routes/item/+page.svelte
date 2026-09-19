<script lang="ts">
	import { page } from '$app/state';
	import { fetchHistory } from '$lib/stores/data.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice, formatDate, shopLabel } from '$lib/utils/format';
	import type { ProductHistory } from '$lib/types';
	import { ArrowLeft, ExternalLink, ArrowDown } from '@lucide/svelte';
	import { base } from '$app/paths';

	let shop = $derived(page.url.searchParams.get('shop') ?? '');
	let sku = $derived(page.url.searchParams.get('sku') ?? '');

	let history = $state<ProductHistory | null>(null);
	let loading = $state(true);

	$effect(() => {
		if (!shop || !sku) {
			loading = false;
			return;
		}
		loading = true;
		fetchHistory(shop, sku).then((data) => {
			history = data;
			loading = false;
		});
	});

	let change = $derived.by(() => {
		if (!history || history.history.length < 2) return null;
		const first = history.history[0].price;
		const last = history.history[history.history.length - 1].price;
		if (first === last) return null;
		return { delta: last - first, pct: ((last - first) / first) * 100 };
	});
</script>

<svelte:head>
	<title>{history?.product.title ?? 'История цены'} — skidki</title>
</svelte:head>

<a
	href="{base}/deals"
	class="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200"
>
	<ArrowLeft class="h-4 w-4" /> К скидкам
</a>

{#if loading}
	<div class="flex h-64 items-center justify-center">
		<span class="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-amber-500"></span>
	</div>
{:else if !history}
	<div class="rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-center text-slate-400">
		История этого товара ещё не собрана — нужен хотя бы один обход.
	</div>
{:else}
	<div class="mb-5 flex gap-4">
		{#if history.product.image}
			<img
				src={history.product.image}
				alt={history.product.title}
				loading="lazy"
				referrerpolicy="no-referrer"
				class="h-28 w-28 shrink-0 rounded-xl border border-slate-700/50 bg-slate-900/60 object-cover"
			/>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<span class="rounded bg-slate-700/60 px-2 py-0.5 text-xs text-slate-300">
					{shopLabel(history.product.shop)}
				</span>
				{#if history.product.brand}
					<span class="text-xs text-slate-500">{history.product.brand}</span>
				{/if}
				{#if history.product.category}
					<span class="text-xs text-slate-500">· {history.product.category}</span>
				{/if}
			</div>
			<h1 class="mt-2 text-lg font-bold text-slate-100">{history.product.title}</h1>
			<div class="mt-3 flex flex-wrap items-baseline gap-3">
				<span class="text-3xl font-black text-amber-400">
					{formatPrice(history.product.price)}
				</span>
				{#if change}
					<span
						class="flex items-center gap-1 text-sm font-medium {change.delta < 0
							? 'text-emerald-400'
							: 'text-red-400'}"
					>
						{#if change.delta < 0}<ArrowDown class="h-4 w-4" />{/if}
						{formatPrice(Math.abs(change.delta))} ({change.pct.toFixed(1)}%)
					</span>
				{/if}
				<a
					href={history.product.url}
					target="_blank"
					rel="noopener"
					class="flex items-center gap-1 text-sm text-slate-400 hover:text-amber-400"
				>
					<ExternalLink class="h-4 w-4" /> В магазине
				</a>
			</div>
		</div>
	</div>

	<section class="mb-6 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
		<h2 class="mb-4 text-sm font-semibold text-slate-300">История цены</h2>
		<PriceChart
			data={history.history}
			height={260}
			labelFormatter={(d) => (d.length >= 10 ? formatDate(d) : d)}
		/>
	</section>

	<section class="grid gap-3 sm:grid-cols-3">
		<div class="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
			<p class="text-xs text-slate-500">Минимум за период</p>
			<p class="mt-1 text-lg font-bold text-emerald-400">
				{formatPrice(history.stats.min_90d)}
			</p>
		</div>
		<div class="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
			<p class="text-xs text-slate-500">Медиана</p>
			<p class="mt-1 text-lg font-bold text-slate-200">
				{formatPrice(history.stats.median_30d)}
			</p>
		</div>
		<div class="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
			<p class="text-xs text-slate-500">Точек наблюдения</p>
			<p class="mt-1 text-lg font-bold text-slate-200">{history.history.length}</p>
		</div>
	</section>
{/if}