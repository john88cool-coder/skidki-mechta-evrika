<script lang="ts">
	import { base } from '$app/paths';
	import type { Deal } from '$lib/types';
	import { formatPrice, formatPct, shopLabel } from '$lib/utils/format';
	import { ExternalLink, LineChart } from '@lucide/svelte';

	interface Props {
		deal: Deal;
		rank?: number;
	}

	let { deal, rank = 0 }: Props = $props();

	let product = $derived(deal.product);
	let hasDiscount = $derived(
		!!product.old_price && product.old_price > product.price
	);
	let historyHref = $derived(`${base}/item?shop=${product.shop}&sku=${product.sku}`);
</script>

<div
	class="card-hover relative rounded-xl border border-slate-700/50 bg-slate-800/80 p-4 backdrop-blur"
>
	<div class="flex items-start justify-between gap-3">
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				{#if rank > 0}
					<span class="text-xs font-bold text-slate-500">#{rank}</span>
				{/if}
				<span class="rounded bg-slate-700/60 px-1.5 py-0.5 text-xs text-slate-300">
					{shopLabel(product.shop)}
				</span>
				{#if !product.in_stock}
					<span class="rounded bg-red-500/20 px-1.5 py-0.5 text-xs text-red-300">
						нет в наличии
					</span>
				{/if}
			</div>

			<h3 class="mt-2 line-clamp-2 text-sm font-medium text-slate-200" title={product.title}>
				{product.title}
			</h3>

			<div class="mt-3 flex items-baseline gap-2">
				<span class="text-2xl font-bold text-amber-400">{formatPrice(product.price)}</span>
				{#if hasDiscount}
					<span class="text-sm text-slate-500 line-through">
						{formatPrice(product.old_price!)}
					</span>
				{/if}
			</div>
		</div>

		<div class="flex flex-col items-end gap-2">
			{#if hasDiscount}
				<span class="text-3xl font-black text-amber-500">{formatPct(deal.drop_pct ?? 0)}</span>
			{/if}
			<div class="flex gap-1">
				<a
					href={historyHref}
					class="rounded p-1 text-slate-500 transition-colors hover:bg-slate-700 hover:text-amber-400"
					title="История цены"
					aria-label="История цены"
				>
					<LineChart class="h-4 w-4" />
				</a>
				<a
					href={product.url}
					target="_blank"
					rel="noopener"
					class="rounded p-1 text-slate-500 transition-colors hover:bg-slate-700 hover:text-slate-200"
					title="Открыть в магазине"
					aria-label="Открыть в магазине"
				>
					<ExternalLink class="h-4 w-4" />
				</a>
			</div>
		</div>
	</div>
</div>

