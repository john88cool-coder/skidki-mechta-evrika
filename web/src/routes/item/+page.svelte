<script lang="ts">
	import { page } from '$app/state';
	import { dashboard, fetchHistory } from '$lib/stores/data.svelte';
	import { recentPrices, formatChange } from '$lib/utils/history';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice, formatDate, shopLabel } from '$lib/utils/format';
	import type { ProductHistory } from '$lib/types';
	import { ArrowLeft, ExternalLink, ArrowDown } from '@lucide/svelte';
	import { base } from '$app/paths';

	let shop = $derived(page.url.searchParams.get('shop') ?? '');
	let sku = $derived(page.url.searchParams.get('sku') ?? '');
	let backHref = $derived.by(() => {
		const from = page.url.searchParams.get('from');
		if (!from?.startsWith(`${base}/`)) return `${base}/deals`;
		const target = new URL(from, page.url.origin);
		return target.origin === page.url.origin && [base + '/', base + '/deals'].includes(target.pathname) ? target.pathname + target.search : `${base}/deals`;
	});

	let history = $state<ProductHistory | null>(null);
	let loading = $state(true);

	$effect(() => {
		const version = dashboard.data?.updated_at;
		if (!shop || !sku) {
			loading = false;
			return;
		}
		loading = true;
		let cancelled = false;
		fetchHistory(shop, sku).then((data) => {
			if (!cancelled) { history = data; loading = false; }
		});
		return () => { cancelled = true; };
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
	href={backHref}
	class="mb-4 inline-flex items-center gap-1.5 text-sm text-stone-600 hover:text-slate-800"
>
	<ArrowLeft class="h-4 w-4" /> К скидкам
</a>

{#if loading}
	<div class="flex h-64 items-center justify-center">
		<span class="h-8 w-8 animate-spin rounded-full border-4 border-stone-300 border-t-amber-500"></span>
	</div>
{:else if !history}
	<div class="rounded-xl border border-stone-200 bg-white p-12 text-center text-stone-600">
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
				class="h-28 w-28 shrink-0 rounded-xl border border-stone-200 bg-white object-contain p-2"
			/>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<span class="rounded bg-stone-100 px-2 py-0.5 text-xs text-slate-700">
					{shopLabel(history.product.shop)}
				</span>
				{#if history.product.brand}
					<span class="text-xs text-stone-500">{history.product.brand}</span>
				{/if}
				{#if history.product.category}
					<span class="text-xs text-stone-500">· {history.product.category}</span>
				{/if}
			</div>
			<h1 class="mt-2 text-lg font-bold text-slate-900">{history.product.title}</h1>
			<div class="mt-3 flex flex-wrap items-baseline gap-3">
				<span class="text-3xl font-black text-emerald-800">
					{formatPrice(history.product.price)}
				</span>
				{#if change}
					<span
						class="flex items-center gap-1 text-sm font-medium {change.delta < 0
							? 'text-emerald-700'
							: 'text-red-700'}"
					>
						{#if change.delta < 0}<ArrowDown class="h-4 w-4" />{/if}
						{formatPrice(Math.abs(change.delta))} ({change.pct.toFixed(1)}%)
					</span>
				{/if}
				<a
					href={history.product.url}
					target="_blank"
					rel="noopener"
					class="flex items-center gap-1 text-sm text-stone-600 hover:text-emerald-800"
				>
					<ExternalLink class="h-4 w-4" /> В магазине
				</a>
			</div>
		</div>
	</div>

	<section class="mb-6 rounded-xl border border-stone-200 bg-white p-5">
		<h2 class="mb-4 text-sm font-semibold text-slate-700">История цены</h2>
		<PriceChart
			data={history.history}
			height={260}
			labelFormatter={(d) => (d.length >= 10 ? formatDate(d) : d)}
		/>
	</section>

	<section class="mb-6 rounded-xl border border-stone-200 bg-white p-5">
		<h2 class="mb-3 font-semibold">Последние наблюдения</h2>
		<p class="mb-3 text-xs text-stone-500">Изменение относительно предыдущей записи. Новые наблюдения сверху.</p>
		<div class="overflow-x-auto"><table class="w-full text-left text-sm"><thead><tr class="border-b border-stone-200 text-xs text-stone-500"><th class="py-2">Дата</th><th>Цена</th><th>Изменение</th></tr></thead><tbody>
		{#each recentPrices(history.recent ?? history.history).reverse() as point}<tr class="border-b border-stone-100"><td class="py-3"><time datetime={point.date}>{formatDate(point.date)}</time></td><td>{formatPrice(point.price)}</td><td class:price-down={point.change !== null && point.change < 0} class:price-up={point.change !== null && point.change > 0}>{formatChange(point.change)}</td></tr>{/each}
		</tbody></table></div>
	</section>

	<section class="grid gap-3 sm:grid-cols-3">
		<div class="rounded-xl border border-stone-200 bg-white p-4">
			<p class="text-xs text-stone-500">Минимум за период</p>
			<p class="mt-1 text-lg font-bold text-emerald-700">
				{formatPrice(history.stats.min_90d)}
			</p>
		</div>
		<div class="rounded-xl border border-stone-200 bg-white p-4">
			<p class="text-xs text-stone-500">Медиана</p>
			<p class="mt-1 text-lg font-bold text-slate-800">
				{formatPrice(history.stats.median_30d)}
			</p>
		</div>
		<div class="rounded-xl border border-stone-200 bg-white p-4">
			<p class="text-xs text-stone-500">Точек наблюдения</p>
			<p class="mt-1 text-lg font-bold text-slate-800">{history.history.length}</p>
		</div>
	</section>
{/if}
