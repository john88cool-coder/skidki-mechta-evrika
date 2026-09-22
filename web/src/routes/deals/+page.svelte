<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { untrack } from 'svelte';
	import { dashboard } from '$lib/stores/data.svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { shopLabel, groupLabel, formatPrice } from '$lib/utils/format';
	import { Search, X, SlidersHorizontal, ArrowUpDown, Heart } from '@lucide/svelte';

	const initial = untrack(() => page.url.searchParams);
	let query = $state(initial.get('q') ?? '');
	let shop = $state<string>(initial.get('shop') ?? 'all');
	let group = $state<string>(initial.get('group') ?? 'all');
	let brand = $state<string>(initial.get('brand') ?? 'all');
	let minPct = $state(Math.max(0, Math.min(90, Number(initial.get('min')) || 0)));
	let priceMax = $state<string>(initial.get('pmax') ?? 'all');
	let inStockOnly = $state(initial.get('stock') === '1');
	let badgeFilter = $state<string>(initial.get('badge') ?? 'all');
	let valueSort = false;
	let favOnly = $state(initial.get('fav') === '1');
	let sort = $state<'discount' | 'price' | 'price_desc' | 'title' | 'value'>(
		(initial.get('sort') === 'price' || initial.get('sort') === 'price_desc' || initial.get('sort') === 'title' || initial.get('sort') === 'value'
			? (initial.get('sort') as 'discount' | 'price' | 'price_desc' | 'title' | 'value')
			: 'discount')
	);

	let returnTo = $derived.by(() => {
		const filters: Record<string, string> = {};
		if (query) filters.q = query;
		if (shop !== 'all') filters.shop = shop;
		if (group !== 'all') filters.group = group;
		if (brand !== 'all') filters.brand = brand;
		if (minPct) filters.min = String(minPct);
		if (priceMax !== 'all') filters.pmax = priceMax;
		if (inStockOnly) filters.stock = '1';
		if (badgeFilter !== 'all') filters.badge = badgeFilter;
		if (favOnly) filters.fav = '1';
		if (sort !== 'discount') filters.sort = sort;
		return untrack(() => {
			const url = new URL(page.url);
			for (const k of [...url.searchParams.keys()]) url.searchParams.delete(k);
			for (const [k, v] of Object.entries(filters)) url.searchParams.set(k, v);
			return url.pathname + url.search;
		});
	});
	let filtersInitialized = false;
	$effect(() => {
		const url = returnTo;
		if (!filtersInitialized) { filtersInitialized = true; return; }
		untrack(() => replaceState(url, page.state));
	});

	let shops = $derived(['all', ...new Set(dashboard.deals.map((d) => d.product.shop))]);
	let groups = $derived(['all', ...new Set(dashboard.deals.map((d) => d.product.group ?? 'other'))]);
	let brands = $derived.by(() => {
		const set = new Set<string>();
		for (const d of dashboard.deals) if (d.product.brand) set.add(d.product.brand);
		return ['all', ...[...set].sort((a, b) => a.localeCompare(b, 'ru'))].slice(0, 20);
	});
	const priceBuckets: { value: string; label: string }[] = [
		{ value: 'all', label: 'любая' },
		{ value: '50000', label: 'до 50k' },
		{ value: '100000', label: 'до 100k' },
		{ value: '200000', label: 'до 200k' },
		{ value: '500000', label: 'до 500k' }
	];

	let filtered = $derived.by(() => {
		const needle = query.trim().toLowerCase();
		const max = priceMax === 'all' ? Infinity : Number(priceMax);
		const rows = dashboard.deals.filter((d) => {
			if (shop !== 'all' && d.product.shop !== shop) return false;
			if (group !== 'all' && (d.product.group ?? 'other') !== group) return false;
			if (brand !== 'all' && (d.product.brand ?? '') !== brand) return false;
			if ((d.drop_pct ?? 0) < minPct) return false;
			if (d.product.price > max) return false;
			if (inStockOnly && !d.product.in_stock) return false;
			if (badgeFilter !== 'all' && !(d.badges ?? d.product.badges ?? []).includes(badgeFilter)) return false;
			if (favOnly && !favorites.has(favId(d.product.shop, d.product.sku))) return false;
			if (needle) {
				const hay = `${d.product.title} ${d.product.brand ?? ''} ${d.product.category ?? ''}`.toLowerCase();
				if (!hay.includes(needle)) return false;
			}
			return true;
		});
		return rows.sort((a, b) => {
			if (sort === 'price') return a.product.price - b.product.price;
			if (sort === 'price_desc') return b.product.price - a.product.price;
			if (sort === 'title') return a.product.title.localeCompare(b.product.title, 'ru');
			if (sort === 'value') return (b.value_score ?? b.product.value_score ?? 0) - (a.value_score ?? a.product.value_score ?? 0);
			if ((a as any).valueSort || (b as any).valueSort) {}
			return (b.drop_pct ?? 0) - (a.drop_pct ?? 0);
		});
	});

	function reset() { query = ''; shop = 'all'; group = 'all'; brand = 'all'; badgeFilter='all'; minPct = 0; priceMax = 'all'; inStockOnly = false; favOnly = false; sort = 'discount'; }
	let hasFilters = $derived(query !== '' || shop !== 'all' || group !== 'all' || brand !== 'all' || badgeFilter !== 'all' || minPct > 0 || priceMax !== 'all' || inStockOnly || favOnly || sort !== 'discount');
</script>

<svelte:head><title>Скидки — skidki</title></svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Каталог</p>
		<h1 class="page-heading">Все <em>скидки</em></h1>
		<p class="page-description">Фильтруй по магазину, бренду, цене и наличию. История — внутри карточки. Параметры сохраняются в ссылке.</p>
	</div>
	<div class="flex items-center gap-2 rounded-full px-4 py-2 text-sm" style="background:white; border:1px solid var(--line)">
		<span style="color:var(--ink-4)">Найдено</span>
		<span class="font-mono font-bold" style="color:var(--accent)">{filtered.length}</span>
		<span style="color:var(--ink-4)">из {dashboard.deals.length}</span>
	</div>
</div>

<div class="filters">
	<div class="filters-row">
		<label class="search-wrap">
			<Search size={16} />
			<input type="search" aria-label="Поиск товара" bind:value={query} placeholder="Поиск по названию, бренду…" />
		</label>
		<label class="flex items-center gap-2 text-sm shrink-0" style="color:var(--ink-3)">
			<ArrowUpDown size={14} />
			<select aria-label="Сортировка" bind:value={sort} class="h-10 rounded-full px-3 text-sm font-medium" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink)">
				<option value="discount">По скидке</option>
				<option value="price">Цена ↑</option>
				<option value="price_desc">Цена ↓</option>
				<option value="value">По ценности</option>
				<option value="title">По названию</option>
			</select>
		</label>
		{#if hasFilters}
			<button onclick={reset} class="inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-sm font-semibold shrink-0" style="border:1px solid var(--line); color:var(--ink-3)">
				<X size={14} /> Сбросить
			</button>
		{/if}
	</div>
	<div class="chip-row">
		<span class="chip-label"><SlidersHorizontal size={12} class="inline mr-1" />Магазин</span>
		{#each shops as name (name)}
			<button onclick={() => (shop = name)} aria-pressed={shop === name} class="chip">{name === 'all' ? 'Все' : shopLabel(name)}</button>
		{/each}
	</div>
	<div class="chip-row">
		<span class="chip-label">Группа</span>
		{#each groups as key (key)}
			<button onclick={() => (group = key)} aria-pressed={group === key} class="chip">{key === 'all' ? 'Все' : groupLabel(key)}</button>
		{/each}
	</div>
	<div class="chip-row">
		<span class="chip-label">Бренд</span>
		{#each brands as b (b)}
			<button onclick={() => (brand = b)} aria-pressed={brand === b} class="chip">{b === 'all' ? 'Все' : b}</button>
		{/each}
	</div>
	<div class="chip-row">
		<span class="chip-label">Бейдж</span>
		{#each ['all', 'Выбор ИС', 'Честная скидка', 'Топ-Бренд', 'Рисованная?'] as b (b)}
			<button onclick={() => (badgeFilter = b)} aria-pressed={badgeFilter === b} class="chip">{b === 'all' ? 'Все' : b}</button>
		{/each}
	</div>
	<div class="flex flex-wrap gap-3 items-center">
		<div class="range-wrap">
			<span class="chip-label">Скидка от</span>
			<input type="range" aria-label="Минимальная скидка" min="0" max="90" step="5" bind:value={minPct} />
			<span class="range-val">−{minPct}%</span>
		</div>
		<div class="chip-row">
			<span class="chip-label">Цена</span>
			{#each priceBuckets as b (b.value)}
				<button onclick={() => (priceMax = b.value)} aria-pressed={priceMax === b.value} class="chip">{b.label}</button>
			{/each}
		</div>
	</div>
	<div class="flex flex-wrap gap-2">
		<button onclick={() => (inStockOnly = !inStockOnly)} aria-pressed={inStockOnly} class="chip">{inStockOnly ? '✓ ' : ''}В наличии</button>
		<button onclick={() => (favOnly = !favOnly)} aria-pressed={favOnly} class="chip"><Heart size={12} class="inline mr-1" />Избранное{favorites.count ? ` · ${favorites.count}` : ''}</button>
	</div>
</div>

{#if dashboard.loading && !dashboard.data}
	<div class="product-grid">
		{#each Array(8) as _, i (i)}<SkeletonCard />{/each}
	</div>
{:else if filtered.length}
	<div class="product-grid">
		{#each filtered as deal (deal.product.shop + deal.product.sku)}
			<DealCard {deal} {returnTo} />
		{/each}
	</div>
{:else}
	<div class="rounded-2xl p-12 text-center" style="background:white; border:1px solid var(--line)">
		<p class="font-medium" style="color:var(--ink-2)">Ничего не нашлось</p>
		<p class="text-sm mt-1" style="color:var(--ink-4)">Попробуй изменить фильтры или поиск.</p>
		{#if hasFilters}<button onclick={reset} class="mt-4 text-sm font-semibold underline underline-offset-4" style="color:var(--accent)">Сбросить фильтры</button>{/if}
	</div>
{/if}
