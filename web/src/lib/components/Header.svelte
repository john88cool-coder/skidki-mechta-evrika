<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { dashboard } from '$lib/stores/data.svelte';
	import { favorites } from '$lib/stores/favorites.svelte';
	import { timeAgo } from '$lib/utils/format';
	import { NAV_ITEMS, isActive } from '$lib/utils/nav';
	import { ArrowDownRight, LayoutGrid, Tag, Activity, Heart, Search, Sun, Moon, RefreshCw } from '@lucide/svelte';
	import { theme } from '$lib/stores/theme.svelte';

	interface Props { onsearch?: () => void }
	let { onsearch }: Props = $props();

	const ICONS = { home: LayoutGrid, deals: Tag, shops: Activity, favorites: Heart };

	let freshTitle = $derived(
		dashboard.freshness.newest
			? `Время самого давнего обхода среди магазинов. Самый свежий — ${timeAgo(dashboard.freshness.newest)}.`
			: ''
	);
</script>

<header class="app-header">
	<div class="header-inner">
		<a href="{base}/" class="app-logo" aria-label="skidki — сегодня">
			<span class="logo-mark"><ArrowDownRight size={18} strokeWidth={2.5} /></span>
			<span class="logo-word">skidki</span>
			<span class="logo-sub hidden lg:inline">kz · мониторинг цен</span>
		</a>

		<!-- На телефоне эти же разделы — в нижней панели (TabBar). -->
		<nav class="app-navigation" aria-label="Главная навигация">
			{#each NAV_ITEMS as item (item.key)}
				{@const Icon = ICONS[item.key]}
				<a href="{base}{item.path}" aria-current={isActive(page.url.pathname, item.path, base) ? 'page' : undefined}>
					<Icon size={14} />{item.label}
					{#if item.key === 'favorites' && favorites.count}<span class="fav-badge">{favorites.count}</span>{/if}
				</a>
			{/each}
		</nav>

		<div class="header-actions">
			<button class="icon-btn" onclick={() => onsearch?.()} aria-label="Поиск (Ctrl+K)" title="Поиск · Ctrl+K"><Search size={16} /></button>
			<div class="freshness hidden lg:flex" title={freshTitle}>
				<span class="freshness-dot" class:stale={dashboard.freshness.stale} aria-hidden="true"></span>
				{#if dashboard.freshness.oldest}
					<span>обновлено <strong>{timeAgo(dashboard.freshness.oldest)}</strong></span>
				{:else}
					<span>{dashboard.loading ? 'загрузка…' : 'нет данных'}</span>
				{/if}
			</div>
			<button class="icon-btn refresh-btn" onclick={() => dashboard.refresh()} disabled={dashboard.loading} aria-label="Обновить данные" title="Обновить">
				<RefreshCw size={16} class={dashboard.loading ? 'animate-spin' : ''} />
			</button>
			<button class="icon-btn" onclick={() => theme.toggle()} aria-label={theme.current === 'dark' ? 'Светлая тема' : 'Тёмная тема'} title={theme.current === 'dark' ? 'Светлая тема' : 'Тёмная тема'}>
				{#if theme.current === 'dark'}<Sun size={16} />{:else}<Moon size={16} />{/if}
			</button>
		</div>
	</div>
</header>

<style>
	.fav-badge {
		min-width: 18px; height: 18px; padding: 0 5px;
		border-radius: 999px; display: inline-grid; place-items: center;
		font-family: var(--font-mono); font-size: 11px; font-weight: 700;
		background: var(--accent); color: white; line-height: 1;
	}
	.app-navigation a[aria-current='page'] .fav-badge { background: var(--paper); color: var(--ink); }
</style>
