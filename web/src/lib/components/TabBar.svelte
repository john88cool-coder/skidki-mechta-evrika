<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { favorites } from '$lib/stores/favorites.svelte';
	import { NAV_ITEMS, isActive } from '$lib/utils/nav';
	import { LayoutGrid, Tag, Activity, Heart } from '@lucide/svelte';

	/** Нижняя панель разделов на телефоне: под большим пальцем, шапка остаётся низкой. */
	const ICONS = { home: LayoutGrid, deals: Tag, shops: Activity, favorites: Heart };
</script>

<nav class="tabbar" aria-label="Разделы">
	{#each NAV_ITEMS as item (item.key)}
		{@const Icon = ICONS[item.key]}
		<a href="{base}{item.path}" aria-current={isActive(page.url.pathname, item.path, base) ? 'page' : undefined}>
			<span class="tab-icon">
				<Icon size={20} />
				{#if item.key === 'favorites' && favorites.count}<span class="tab-badge">{favorites.count}</span>{/if}
			</span>
			{item.label}
		</a>
	{/each}
</nav>

<style>
	.tabbar { display: none; }
	@media (max-width: 640px) {
		.tabbar {
			position: fixed; left: 0; right: 0; bottom: 0; z-index: 45;
			display: grid; grid-template-columns: repeat(4, 1fr);
			padding: 6px 8px calc(6px + env(safe-area-inset-bottom));
			background: color-mix(in srgb, var(--paper) 94%, transparent);
			backdrop-filter: blur(16px) saturate(180%);
			-webkit-backdrop-filter: blur(16px) saturate(180%);
			border-top: 1px solid var(--line);
		}
		.tabbar a {
			display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
			min-height: 52px; border-radius: 12px;
			font-size: 12px; font-weight: 600; color: var(--ink-3); text-decoration: none;
		}
		.tabbar a[aria-current='page'] { color: var(--ink); background: var(--paper-2); }
		.tab-icon { position: relative; display: grid; place-items: center; }
		.tab-badge {
			position: absolute; top: -6px; left: 14px;
			min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px;
			display: grid; place-items: center;
			font-family: var(--font-mono); font-size: 11px; font-weight: 700; line-height: 1;
			background: var(--accent-strong); color: #fff;
		}
	}
</style>
