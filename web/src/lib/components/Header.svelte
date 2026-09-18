<script lang="ts">
	import { Flame, RefreshCw } from '@lucide/svelte';
	import { lastUpdate } from '$lib/stores/data';
	import { timeAgo } from '$lib/utils/format';

	interface Props {
		title?: string;
	}

	let { title = 'skidki' }: Props = $props();
</script>

<header class="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/80 backdrop-blur-lg">
	<div class="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
		<div class="flex items-center gap-2">
			<Flame class="h-6 w-6 text-amber-500" />
			<span class="text-lg font-bold text-slate-100">{title}</span>
		</div>

		<div class="flex items-center gap-3 text-sm text-slate-400">
			{#if $lastUpdate}
				<span class="flex items-center gap-1.5">
					<span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
					Онлайн
				</span>
				<span class="text-slate-600">|</span>
				<span>{timeAgo($lastUpdate.toISOString())}</span>
			{/if}
			<button 
				class="btn btn-ghost btn-sm btn-circle" 
				onclick={() => location.reload()}
				title="Обновить"
			>
				<RefreshCw class="h-4 w-4" />
			</button>
		</div>
	</div>
</header>
