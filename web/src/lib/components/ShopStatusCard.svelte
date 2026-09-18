<script lang="ts">
	import type { ShopStatus } from '$lib/types';
	import { timeAgo } from '$lib/utils/format';
	import { CheckCircle2, AlertTriangle, XCircle } from '@lucide/svelte';

	interface Props {
		shop: ShopStatus;
	}

	let { shop }: Props = $props();

	const CONFIG = {
		ok: { icon: CheckCircle2, color: 'text-emerald-400', dot: 'online', hint: 'норма' },
		warning: { icon: AlertTriangle, color: 'text-amber-400', dot: 'warning', hint: 'устарел' },
		error: { icon: XCircle, color: 'text-red-400', dot: 'offline', hint: 'сломан' }
	};

	let config = $derived(CONFIG[shop.status] ?? CONFIG.error);
	let stale = $derived(shop.status !== 'ok');
</script>

<div
	class="flex items-center justify-between rounded-lg border px-4 py-3 {stale
		? shop.status === 'error'
			? 'border-red-500/30 bg-red-500/5'
			: 'border-amber-500/30 bg-amber-500/5'
		: 'border-slate-700/30 bg-slate-800/50'}"
>
	<div class="flex items-center gap-3">
		<div class="pulse-dot {config.dot}"></div>
		<div>
			<span class="font-medium text-slate-200">{shop.label}</span>
			<span class="ml-2 text-xs text-slate-500">{config.hint}</span>
		</div>
	</div>

	<div class="flex items-center gap-4 text-sm sm:gap-6">
		<span class="text-slate-400">{shop.item_count.toLocaleString('ru-RU')} позиций</span>
		<span class="hidden text-slate-500 sm:inline">{timeAgo(shop.last_crawl)}</span>
		<config.icon class="h-5 w-5 {config.color}" />
	</div>
</div>

