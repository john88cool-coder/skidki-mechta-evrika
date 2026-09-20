<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { dashboard } from '$lib/stores/data.svelte';
	import { timeAgo, formatDate, formatTime } from '$lib/utils/format';
	import { ArrowDownRight, RefreshCw, LayoutGrid, Tag, Activity } from '@lucide/svelte';
	const links = [
		{ href: `${base}/`, label: 'Обзор', icon: LayoutGrid },
		{ href: `${base}/deals`, label: 'Скидки', icon: Tag },
		{ href: `${base}/shops`, label: 'Магазины', icon: Activity }
	];
	function active(href: string) { return href === `${base}/` ? page.url.pathname === href : page.url.pathname.startsWith(href); }
</script>

<header class="app-header"><div class="header-inner">
	<a href="{base}/" class="app-logo" aria-label="skidki — обзор"><span class="logo-mark"><ArrowDownRight size={23} /></span>skidki<span class="hidden text-[10px] font-normal tracking-normal text-stone-500 lg:inline">Мониторинг цен</span></a>
	<nav class="app-navigation" aria-label="Главная навигация">{#each links as link}<a href={link.href} aria-current={active(link.href) ? 'page' : undefined}><link.icon size={15} />{link.label}</a>{/each}</nav>
	<div class="header-freshness"><div>{#if dashboard.updatedAt}<span>Данные обновлены</span><strong title={`${formatDate(dashboard.updatedAt.toISOString())}, ${formatTime(dashboard.updatedAt.toISOString())}`}>{timeAgo(dashboard.updatedAt.toISOString())}</strong>{:else}<span>Загружаем данные…</span>{/if}</div><button class="refresh-button" onclick={() => dashboard.refresh()} disabled={dashboard.loading} aria-label="Обновить данные"><RefreshCw size={15} class={dashboard.loading ? 'animate-spin' : ''} /></button></div>
</div></header>
