<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { dashboard } from '$lib/stores/data.svelte';
	import { timeAgo } from '$lib/utils/format';
	import { Flame, RefreshCw, LayoutGrid, List, Activity } from '@lucide/svelte';

	const links = [
		{ href: `${base}/`, label: 'Обзор', icon: LayoutGrid },
		{ href: `${base}/deals`, label: 'Скидки', icon: List },
		{ href: `${base}/shops`, label: 'Магазины', icon: Activity }
	];

	function active(href: string): boolean {
		if (href === `${base}/`) return page.url.pathname === `${base}/`;
		return page.url.pathname.startsWith(href);
	}
</script>

<header class="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/85 backdrop-blur-lg">
	<div class="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
		<a href="{base}/" class="flex shrink-0 items-center gap-2">
			<Flame class="h-6 w-6 text-amber-500" />
			<span class="hidden text-lg font-bold text-slate-100 sm:inline">skidki</span>
		</a>

		<nav class="flex items-center gap-1">
			{#each links as link}
				<a
					href={link.href}
					class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors {active(
						link.href
					)
						? 'bg-slate-800 text-amber-400'
						: 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}"
				>
					<link.icon class="h-4 w-4" />
					<span class="hidden sm:inline">{link.label}</span>
				</a>
			{/each}
		</nav>

		<div class="flex shrink-0 items-center gap-3 text-sm text-slate-400">
			{#if dashboard.updatedAt}
				<span class="flex items-center gap-1.5">
					<span class="h-2 w-2 animate-pulse rounded-full bg-emerald-400"></span>
					<span class="hidden md:inline">{timeAgo(dashboard.updatedAt.toISOString())}</span>
				</span>
			{/if}
			<button
				class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
				onclick={() => dashboard.refresh()}
				title="Обновить"
				aria-label="Обновить"
			>
				<RefreshCw class="h-4 w-4 {dashboard.loading ? 'animate-spin' : ''}" />
			</button>
		</div>
	</div>
</header>

