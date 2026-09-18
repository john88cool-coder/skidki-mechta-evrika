<script lang="ts">
	import type { ShopStatus } from '$lib/types';
	import { timeAgo } from '$lib/utils/format';
	import { CheckCircle2, AlertTriangle, XCircle } from '@lucide/svelte';

	interface Props {
		shop: ShopStatus;
	}

	let { shop }: Props = $props();

	let statusConfig = $derived({
		ok: { icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-400/10', dot: 'online' },
		warning: { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'warning' },
		error: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-400/10', dot: 'offline' }
	}[shop.status]);
</script>

<div class="flex items-center justify-between rounded-lg bg-slate-800/50 px-4 py-3 border border-slate-700/30">
	<div class="flex items-center gap-3">
		<div class="pulse-dot {statusConfig.dot}"></div>
		<span class="font-medium text-slate-200">{shop.label}</span>
	</div>
	
	<div class="flex items-center gap-6 text-sm">
		<span class="text-slate-400">{shop.item_count.toLocaleString()} позиций</span>
		<span class="text-slate-500">{timeAgo(shop.last_crawl)}</span>
		<statusConfig.icon class="h-5 w-5 {statusConfig.color}" />
	</div>
</div>
