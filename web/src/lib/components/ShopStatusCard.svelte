<script lang="ts">
	import type { ShopStatus } from '$lib/types';
	import { timeAgo } from '$lib/utils/format';
	import { CheckCircle2, AlertTriangle, XCircle } from '@lucide/svelte';

	interface Props {
		shop: ShopStatus;
	}

	let { shop }: Props = $props();

	const CONFIG = {
		ok: { icon: CheckCircle2, color: 'text-emerald-700', dot: 'online', hint: 'норма' },
		warning: { icon: AlertTriangle, color: 'text-amber-700', dot: 'warning', hint: 'устарел' },
		error: { icon: XCircle, color: 'text-red-700', dot: 'offline', hint: 'нет успешного обхода' }
	};

	let config = $derived(CONFIG[shop.status] ?? CONFIG.error);
	let stale = $derived(shop.status !== 'ok');
</script>

<div
	class="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 {stale
		? shop.status === 'error'
			? 'border-red-500/30 bg-red-500/5'
			: 'border-amber-500/30 bg-amber-500/5'
		: 'border-stone-200 bg-white'}"
>
	<div class="flex items-center gap-3">
		<div class="pulse-dot {config.dot}"></div>
		<div>
			<span class="font-medium text-slate-800">{shop.label}</span>
			<span class="ml-2 text-xs text-stone-500">{config.hint}</span>
		</div>
	</div>

	<div class="flex items-center gap-4 text-sm sm:gap-6">
		<span class="text-stone-600">{shop.item_count.toLocaleString('ru-RU')} позиций</span>
		{#if shop.status !== 'error'}<span class="text-xs text-stone-500">{timeAgo(shop.last_crawl)}</span>{/if}
		<config.icon class="h-5 w-5 {config.color}" />
	</div>
</div>

