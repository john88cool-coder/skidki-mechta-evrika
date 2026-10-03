<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { untrack } from 'svelte';
	import { dashboard } from '$lib/stores/data.svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { shopLabel, groupLabel } from '$lib/utils/format';
	import { verdictOf, realRank, VERDICT_LABELS, type VerdictKind } from '$lib/utils/verdict';
	import { byNovelty } from '$lib/utils/novelty';
	import { Search, X, SlidersHorizontal, ArrowUpDown, Heart, ChevronDown } from '@lucide/svelte';

	type SortKey = 'real' | 'new' | 'claimed' | 'price' | 'price_desc' | 'title';
	type VerdictFilter = 'all' | 'real' | VerdictKind;
	const SORTS: SortKey[] = ['real', 'new', 'claimed', 'price', 'price_desc', 'title'];
	const VERDICT_FILTERS: VerdictFilter[] = ['all', 'real', 'honest', 'inflated', 'painted', 'unknown'];
	const PAGE = 24;

	const initial = untrack(() => page.url.searchParams);
	let query = $state(initial.get('q') ?? '');
	let shop = $state<string>(initial.get('shop') ?? 'all');
	let group = $state<string>(initial.get('group') ?? 'all');
	let brand = $state<string>(initial.get('brand') ?? 'all');
	let minPct = $state(Math.max(0, Math.min(90, Number(initial.get('min')) || 0)));
	let priceMax = $state<string>(initial.get('pmax') ?? 'all');
	let inStockOnly = $state(initial.get('stock') === '1');
	let favOnly = $state(initial.get('fav') === '1');
	let verdictFilter = $state<VerdictFilter>(
		VERDICT_FILTERS.includes(initial.get('v') as VerdictFilter) ? (initial.get('v') as VerdictFilter) : 'all'
	);
	let sort = $state<SortKey>(SORTS.includes(initial.get('sort') as SortKey) ? (initial.get('sort') as SortKey) : 'real');
	let limit = $state(PAGE);

	let returnTo = $derived.by(() => {
		const filters: Record<string, string> = {};
		if (query) filters.q = query;
		if (shop !== 'all') filters.shop = shop;
		if (group !== 'all') filters.group = group;
		if (brand !== 'all') filters.brand = brand;
		if (minPct) filters.min = String(minPct);
		if (priceMax !== 'all') filters.pmax = priceMax;
		if (inStockOnly) filters.stock = '1';
		if (favOnly) filters.fav = '1';
		if (verdictFilter !== 'all') filters.v = verdictFilter;
		if (sort !== 'real') filters.sort = sort;
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
		// Новый набор фильтров — снова первая «страница».
		untrack(() => { limit = PAGE; replaceState(url, page.state); });
	});

	let shops = $derived(['all', ...new Set(dashboard.deals.map((d) => d.product.shop))]);
	let groups = $derived(['all', ...new Set(dashboard.deals.map((d) => d.product.group ?? 'other'))]);
	let brands = $derived.by(() => {
		const count = new Map<string, number>();
		for (const d of dashboard.deals) if (d.product.brand) count.set(d.product.brand, (count.get(d.product.brand) ?? 0) + 1);
		return [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ru'));
	});
	const priceBuckets = [
		{ value: 'all', label: 'любая' },
		{ value: '50000', label: 'до 50 тыс.' },
		{ value: '100000', label: 'до 100 тыс.' },
		{ value: '200000', label: 'до 200 тыс.' },
		{ value: '500000', label: 'до 500 тыс.' }
	];
	const SORT_LABELS: Record<SortKey, string> = {
		real: 'Реальная выгода',
		new: 'Сначала новинки',
		claimed: 'Скидка на ценнике',
		price: 'Сначала дешевле',
		price_desc: 'Сначала дороже',
		title: 'По названию'
	};
	const FILTER_LABELS: Record<VerdictFilter, string> = {
		all: 'Все',
		real: 'Реально подешевело',
		...VERDICT_LABELS
	};

	function matchesVerdict(kind: VerdictKind, filter: VerdictFilter): boolean {
		if (filter === 'all') return true;
		if (filter === 'real') return kind === 'honest' || kind === 'inflated';
		return kind === filter;
	}

	/** Все фильтры, кроме вердикта: от них считаются счётчики на чипах вердикта. */
	let base = $derived.by(() => {
		const needle = query.trim().toLowerCase();
		const max = priceMax === 'all' ? Infinity : Number(priceMax);
		return dashboard.deals.filter((d) => {
			if (shop !== 'all' && d.product.shop !== shop) return false;
			if (group !== 'all' && (d.product.group ?? 'other') !== group) return false;
			if (brand !== 'all' && (d.product.brand ?? '') !== brand) return false;
			const v = verdictOf(d);
			if ((v.real || v.claimed || 0) < minPct) return false;
			if (d.product.price > max) return false;
			if (inStockOnly && !d.product.in_stock) return false;
			if (favOnly && !favorites.has(favId(d.product.shop, d.product.sku))) return false;
			if (needle) {
				const hay = `${d.product.title} ${d.product.brand ?? ''} ${d.product.category ?? ''}`.toLowerCase();
				if (!hay.includes(needle)) return false;
			}
			return true;
		});
	});
	let counts = $derived.by(() => {
		const out = Object.fromEntries(VERDICT_FILTERS.map((f) => [f, 0])) as Record<VerdictFilter, number>;
		for (const d of base) {
			const kind = verdictOf(d).kind;
			for (const f of VERDICT_FILTERS) if (matchesVerdict(kind, f)) out[f] += 1;
		}
		return out;
	});
	let filtered = $derived.by(() => {
		const rows = base.filter((d) => matchesVerdict(verdictOf(d).kind, verdictFilter));
		return rows.sort((a, b) => {
			if (sort === 'new') return byNovelty(a, b);
			if (sort === 'price') return a.product.price - b.product.price;
			if (sort === 'price_desc') return b.product.price - a.product.price;
			if (sort === 'title') return a.product.title.localeCompare(b.product.title, 'ru');
			if (sort === 'claimed') return (b.drop_pct ?? 0) - (a.drop_pct ?? 0);
			return realRank(b) - realRank(a);
		});
	});
	let visible = $derived(filtered.slice(0, limit));

	function reset() {
		query = ''; shop = 'all'; group = 'all'; brand = 'all'; minPct = 0; priceMax = 'all';
		inStockOnly = false; favOnly = false; verdictFilter = 'all'; sort = 'real';
	}
	let hasFilters = $derived(
		query !== '' || shop !== 'all' || group !== 'all' || brand !== 'all' || minPct > 0 || priceMax !== 'all' ||
			inStockOnly || favOnly || verdictFilter !== 'all' || sort !== 'real'
	);
</script>

<svelte:head><title>Каталог скидок — skidki</title></svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Каталог</p>
		<h1 class="page-heading">Все <em>скидки</em></h1>
		<p class="page-description">
			У каждой позиции — вердикт по истории цены: <strong>честная</strong>, <strong>завышена</strong>,
			<strong>нарисована</strong> или пока <strong>без истории</strong>. Фильтры сохраняются в ссылке.
		</p>
	</div>
	<div class="found-pill">
		<span>Найдено</span><strong>{filtered.length}</strong><span>из {dashboard.deals.length}</span>
	</div>
</div>

<div class="filters">
	<div class="filters-row">
		<label class="search-wrap">
			<Search size={16} />
			<input type="search" aria-label="Поиск товара" bind:value={query} placeholder="Поиск по названию, бренду, категории…" />
		</label>
		<label class="select-wrap">
			<ArrowUpDown size={14} />
			<select aria-label="Сортировка" bind:value={sort}>
				{#each SORTS as key (key)}<option value={key}>{SORT_LABELS[key]}</option>{/each}
			</select>
			<ChevronDown size={14} />
		</label>
		{#if hasFilters}
			<button onclick={reset} class="reset-btn"><X size={14} /> Сбросить</button>
		{/if}
	</div>

	<div class="chip-row" role="group" aria-label="Вердикт">
		<span class="chip-label">Вердикт</span>
		{#each VERDICT_FILTERS as key (key)}
			<button onclick={() => (verdictFilter = key)} aria-pressed={verdictFilter === key} class="chip verdict-filter {key}" disabled={key !== 'all' && counts[key] === 0 && verdictFilter !== key}>
				{FILTER_LABELS[key]}<span class="chip-count">{counts[key]}</span>
			</button>
		{/each}
	</div>
	<div class="chip-row" role="group" aria-label="Магазин">
		<span class="chip-label"><SlidersHorizontal size={12} class="inline mr-1" />Магазин</span>
		{#each shops as name (name)}
			<button onclick={() => (shop = name)} aria-pressed={shop === name} class="chip">{name === 'all' ? 'Все' : shopLabel(name)}</button>
		{/each}
	</div>
	<div class="chip-row" role="group" aria-label="Группа">
		<span class="chip-label">Группа</span>
		{#each groups as key (key)}
			<button onclick={() => (group = key)} aria-pressed={group === key} class="chip">{key === 'all' ? 'Все' : groupLabel(key)}</button>
		{/each}
	</div>
	<div class="filters-foot">
		<label class="select-wrap compact">
			<span class="chip-label">Бренд</span>
			<select aria-label="Бренд" bind:value={brand}>
				<option value="all">Все бренды</option>
				{#each brands as [name, n] (name)}<option value={name}>{name} · {n}</option>{/each}
			</select>
			<ChevronDown size={14} />
		</label>
		<div class="range-wrap">
			<span class="chip-label">Скидка от</span>
			<input type="range" aria-label="Минимальная скидка" min="0" max="80" step="5" bind:value={minPct} />
			<span class="range-val">{minPct ? `−${minPct}%` : 'любая'}</span>
		</div>
		<div class="chip-row" role="group" aria-label="Цена">
			<span class="chip-label">Цена</span>
			{#each priceBuckets as b (b.value)}
				<button onclick={() => (priceMax = b.value)} aria-pressed={priceMax === b.value} class="chip">{b.label}</button>
			{/each}
		</div>
		<button onclick={() => (inStockOnly = !inStockOnly)} aria-pressed={inStockOnly} class="chip">В наличии</button>
		<button onclick={() => (favOnly = !favOnly)} aria-pressed={favOnly} class="chip"><Heart size={12} class="inline mr-1" />Избранное{favorites.count ? ` · ${favorites.count}` : ''}</button>
	</div>
</div>

{#if dashboard.loading && !dashboard.data}
	<div class="product-grid">
		{#each Array(8) as _, i (i)}<SkeletonCard />{/each}
	</div>
{:else if filtered.length}
	<div class="product-grid">
		{#each visible as deal (deal.product.shop + deal.product.sku)}
			<DealCard {deal} {returnTo} />
		{/each}
	</div>
	{#if filtered.length > limit}
		<div class="more-row">
			<button class="section-link" onclick={() => (limit += PAGE)}>
				Показать ещё {Math.min(PAGE, filtered.length - limit)} <span style="color:var(--ink-4)">· осталось {filtered.length - limit}</span>
			</button>
		</div>
	{/if}
{:else}
	<div class="empty-state">
		<p class="font-medium" style="color:var(--ink-2)">Ничего не нашлось</p>
		<p class="text-sm mt-1" style="color:var(--ink-4)">Ослабьте фильтры или поиск.</p>
		{#if hasFilters}<button onclick={reset} class="section-link mt-4">Сбросить фильтры</button>{/if}
	</div>
{/if}
