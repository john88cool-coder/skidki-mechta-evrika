<script lang="ts">
	import type { Deal } from '$lib/types';
	import { formatPrice, formatPct, shopLabel } from '$lib/utils/format';
	import { ExternalLink } from '@lucide/svelte';

	interface Props {
		deal: Deal;
		rank?: number;
	}

	let { deal, rank = 0 }: Props = $props();

	let product = $derived(deal.product);
	let hasDiscount = $derived(product.old_price && product.old_price > product.price);
</script>

<a
	href={product.url}
	target="_blank"
	rel="noopener"
	class="card-hover block rounded-xl bg-slate-800/80 p-4 backdrop-blur border border-slate-700/50"
>
	<div class="flex items-start justify-between gap-3">
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				{#if rank > 0}
					<span class="text-xs font-bold text-slate-500">#{rank}</span>
				{/if}
				<span class="badge badge-sm badge-ghost text-slate-400">
					{shopLabel(product.shop)}
				</span>
				{#if !product.in_stock}
					<span class="badge badge-sm badge-error">Нет в наличии</span>
				{/if}
			</div>
			
			<h3 class="mt-2 truncate text-sm font-medium text-slate-200" title={product.title}>
				{product.title}
			</h3>
			
			<div class="mt-3 flex items-baseline gap-2">
				<span class="text-2xl font-bold text-amber-400">
					{formatPrice(product.price)}
				</span>
				{#if hasDiscount}
					<span class="text-sm text-slate-500 line-through">
						{formatPrice(product.old_price!)}
					</span>
				{/if}
			</div>
		</div>

		<div class="flex flex-col items-end gap-1">
			{#if hasDiscount}
				<span class="text-3xl font-black text-amber-500">
					{formatPct(deal.drop_pct ?? 0)}
				</span>
			{/if}
			<ExternalLink class="h-4 w-4 text-slate-600" />
		</div>
	</div>
</a>
