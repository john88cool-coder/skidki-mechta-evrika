<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { dashboard } from '$lib/stores/data.svelte';
	import { favorites } from '$lib/stores/favorites.svelte';
	import { compare } from '$lib/stores/compare.svelte';
	import { timeAgo } from '$lib/utils/format';
	import { ArrowDownRight, LayoutGrid, Tag, Activity, Heart, Scale, Trophy, Search, Sun, Moon, RefreshCw } from '@lucide/svelte';
	import { theme } from '$lib/stores/theme.svelte';

	interface Props { onsearch?: () => void }
	let { onsearch }: Props = $props();

	const links = [
		{ href: `${base}/`, label: 'Обзор', icon: LayoutGrid },
		{ href: `${base}/top`, label: 'Топ', icon: Trophy },
		{ href: `${base}/deals`, label: 'Каталог', icon: Tag },
		{ href: `${base}/compare`, label: 'Сравнение', icon: Scale, badge: () => compare.count },
		{ href: `${base}/shops`, label: 'Магазины', icon: Activity },
		{ href: `${base}/favorites`, label: 'Избранное', icon: Heart, badge: () => favorites.count }
	];
	function active(href: string) {
		return href === `${base}/` ? page.url.pathname === href : page.url.pathname.startsWith(href);
	}
</script>

<header class="app-header">
	<div class="header-inner">
		<a href="{base}/" class="app-logo" aria-label="skidki — обзор">
			<span class="logo-mark"><ArrowDownRight size={18} strokeWidth={2.5} /></span>
			<span class="logo-word">skidki</span>
			<span class="logo-sub hidden sm:inline">kz · мониторинг цен</span>
		</a>

		<nav class="app-navigation" aria-label="Главная навигация">
			{#each links as link}
				{@const badge = (link as any).badge ? (link as any).badge() : 0}
				<a href={link.href} aria-current={active(link.href) ? 'page' : undefined}>
					<link.icon size={14} />{link.label}
					{#if badge}<span class="fav-badge">{badge}</span>{/if}
				</a>
			{/each}
		</nav>

		<div class="header-actions">
			<button class="icon-btn hidden sm:grid" onclick={() => onsearch?.()} aria-label="Поиск (⌘K)" title="Поиск ⌘K"><Search size={15} /></button>
			<div class="freshness hidden lg:flex">
				<span class="freshness-dot" aria-hidden="true"></span>
				{#if dashboard.updatedAt}
					<span>обновлено <strong>{timeAgo(dashboard.updatedAt.toISOString())}</strong></span>
				{:else}
					<span>загрузка…</span>
				{/if}
			</div>
			<button class="icon-btn" onclick={() => dashboard.refresh()} disabled={dashboard.loading} aria-label="Обновить данные" title="Обновить">
				<RefreshCw size={15} class={dashboard.loading ? 'animate-spin' : ''} />
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
		font-family: var(--font-mono); font-size: 10px; font-weight: 700;
		background: var(--accent); color: white; line-height: 1;
	}
	.app-navigation a[aria-current='page'] .fav-badge { background: var(--paper); color: var(--ink); }
</style>
