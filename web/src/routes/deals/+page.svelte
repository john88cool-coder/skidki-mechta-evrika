<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { untrack } from 'svelte';
	import { dashboard } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import { shopLabel, groupLabel, formatPrice } from '$lib/utils/format';
	import { Search, X } from '@lucide/svelte';

	const initial = untrack(() => page.url.searchParams);
	let query = $state(initial.get('q') ?? '');
	let shop = $state<string>(initial.get('shop') ?? 'all');
	let group = $state<string>(initial.get('group') ?? 'all');
	let minPct = $state(Math.max(0, Math.min(90, Number(initial.get('min')) || 0)));
	let sort = $state<'discount' | 'price' | 'title'>(initial.get('sort') === 'price' ? 'price' : initial.get('sort') === 'title' ? 'title' : 'discount');

	let returnTo = $derived.by(() => {
		const filters = { q: query, shop, group, min: minPct, sort };
		return untrack(() => {
			const url = new URL(page.url);
			for (const [key, value] of Object.entries(filters)) {
				if (!value || value === 'all' || value === 'discount') url.searchParams.delete(key);
				else url.searchParams.set(key, String(value));
			}
			return url.pathname + url.search;
		});
	});
	let filtersInitialized = false;
	$effect(() => {
		const url = returnTo;
		// The router is not ready during the initial hydration effect.
		if (!filtersInitialized) { filtersInitialized = true; return; }
		untrack(() => replaceState(url, page.state));
	});

	let shops = $derived(['all', ...new Set(dashboard.deals.map((d) => d.product.shop))]);
	let groups = $derived([
		'all',
		...new Set(dashboard.deals.map((d) => d.product.group ?? 'other'))
	]);

	let filtered = $derived.by(() => {
		const needle = query.trim().toLowerCase();
		const rows = dashboard.deals.filter((d) => {
			if (shop !== 'all' && d.product.shop !== shop) return false;
			if (group !== 'all' && (d.product.group ?? 'other') !== group) return false;
			if ((d.drop_pct ?? 0) < minPct) return false;
			if (needle && !d.product.title.toLowerCase().includes(needle)) return false;
			return true;
		});
		return rows.sort((a, b) => {
			if (sort === 'price') return a.product.price - b.product.price;
			if (sort === 'title') return a.product.title.localeCompare(b.product.title, 'ru');
			return (b.drop_pct ?? 0) - (a.drop_pct ?? 0);
		});
	});

	function reset() {
		query = '';
		shop = 'all';
		group = 'all';
		minPct = 0;
		sort = 'discount';
	}

	let hasFilters = $derived(
		query !== '' || shop !== 'all' || group !== 'all' || minPct > 0 || sort !== 'discount'
	);
</script>

<svelte:head>
	<title>Скидки — skidki</title>
</svelte:head>

<div class="mb-5 flex flex-wrap items-center justify-between gap-3">
	<div><p class="page-eyebrow">Каталог предложений</p><h1 class="page-heading">Все скидки</h1><p class="page-description">Фотографии, цены и история наблюдений в одной карточке.</p></div>
	<span class="text-sm text-stone-600">
		<span class="font-semibold text-emerald-800">{filtered.length}</span>
		из {dashboard.deals.length}
	</span>
</div>

<!-- Фильтры -->
<div class="mb-6 space-y-4 rounded-xl border border-stone-200 bg-white p-4">
	<div class="flex flex-wrap gap-3">
		<label class="relative min-w-[220px] flex-1">
			<Search class="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-stone-500" />
			<input
				type="search"
				aria-label="Поиск товара"
				bind:value={query}
				placeholder="Поиск по названию…"
				class="w-full rounded-lg border border-stone-300 bg-stone-100 py-2 pr-3 pl-9 text-sm text-slate-900 placeholder:text-stone-500 focus:border-emerald-700 focus:outline-none"
			/>
		</label>

		<select
			aria-label="Сортировка"
			bind:value={sort}
			class="rounded-lg border border-stone-300 bg-stone-100 px-3 py-2 text-sm text-slate-900 focus:border-emerald-700 focus:outline-none"
		>
			<option value="discount">По скидке</option>
			<option value="price">По цене</option>
			<option value="title">По названию</option>
		</select>

		{#if hasFilters}
			<button
				onclick={reset}
				class="flex items-center gap-1.5 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-600 hover:bg-stone-100 hover:text-slate-800"
			>
				<X class="h-4 w-4" /> Сбросить
			</button>
		{/if}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<span class="text-xs text-stone-500">Магазин:</span>
		{#each shops as name (name)}
			<button
				onclick={() => (shop = name)}
				aria-pressed={shop === name}
				class="rounded-full px-3 py-1 text-xs transition-colors {shop === name
					? 'bg-emerald-700 text-white'
					: 'bg-stone-100 text-stone-600 hover:text-slate-800'}"
			>
				{name === 'all' ? 'все' : shopLabel(name)}
			</button>
		{/each}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<span class="text-xs text-stone-500">Группа:</span>
		{#each groups as key (key)}
			<button
				onclick={() => (group = key)}
				aria-pressed={group === key}
				class="rounded-full px-3 py-1 text-xs transition-colors {group === key
					? 'bg-emerald-700 text-white'
					: 'bg-stone-100 text-stone-600 hover:text-slate-800'}"
			>
				{key === 'all' ? 'все' : groupLabel(key)}
			</button>
		{/each}
	</div>

	<div class="flex items-center gap-3">
		<span class="text-xs text-stone-500">Скидка от</span>
		<input
			type="range"
			aria-label="Минимальная скидка, процентов"
			min="0"
			max="90"
			step="5"
			bind:value={minPct}
			class="h-1.5 w-40 cursor-pointer accent-emerald-700"
		/>
		<span class="w-10 text-sm font-medium text-emerald-800">−{minPct}%</span>
	</div>
</div>

{#if filtered.length}
	<div class="product-grid">
		{#each filtered as deal (deal.product.shop + deal.product.sku)}
			<DealCard {deal} {returnTo} />
		{/each}
	</div>
{:else}
	<div class="rounded-xl border border-stone-200 bg-white p-12 text-center">
		<p class="text-stone-600">Ничего не нашлось</p>
		{#if hasFilters}
			<button onclick={reset} class="mt-3 text-sm text-emerald-800 hover:text-emerald-900">
				Сбросить фильтры
			</button>
		{/if}
	</div>
{/if}
