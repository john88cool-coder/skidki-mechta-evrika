<script lang="ts">
	import type { ShopStatus } from '$lib/types';
	import { timeAgo } from '$lib/utils/format';
	import { CheckCircle2, AlertTriangle, XCircle } from '@lucide/svelte';

	interface Props { shop: ShopStatus; }
	let { shop }: Props = $props();

	const CONFIG = {
		ok: { icon: CheckCircle2, dot: 'online', hint: 'актуально', color: 'text-emerald-600' },
		warning: { icon: AlertTriangle, dot: 'warning', hint: 'устарело', color: 'text-amber-600' },
		error: { icon: XCircle, dot: 'offline', hint: 'требует проверки', color: 'text-red-600' }
	};
	let config = $derived(CONFIG[shop.status] ?? CONFIG.error);
	let stale = $derived(shop.status !== 'ok');
</script>

<div class="shop-card" class:opacity-60={shop.status === 'error'}>
	<div class="flex items-center gap-3 min-w-0">
		<span class="pulse-dot {config.dot}" aria-hidden="true"></span>
		<span class="font-semibold text-[15px] tracking-tight" style="color:var(--ink)">{shop.label}</span>
		<span class="hidden sm:inline text-xs px-2 py-0.5 rounded-full border" style="border-color:var(--line); color:var(--ink-4)">{config.hint}</span>
	</div>
	<div class="flex items-center gap-4 text-sm shrink-0">
		<span style="color:var(--ink-3)">{shop.item_count.toLocaleString('ru-RU')} поз.</span>
		{#if shop.status !== 'error'}<span class="text-xs hidden sm:inline" style="color:var(--ink-4)">{timeAgo(shop.last_crawl)}</span>{/if}
		<config.icon class="h-[18px] w-[18px] {config.color}" />
	</div>
</div>
{#if stale && shop.error}
	<p class="mt-2 text-xs truncate" style="color:var(--accent)">⚠ {shop.error}</p>
{/if}
