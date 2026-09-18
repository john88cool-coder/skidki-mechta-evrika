<script lang="ts">
	import { dashboard } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import { shopLabel, groupLabel, formatPrice } from '$lib/utils/format';
	import { Search, X } from '@lucide/svelte';

	let query = $state('');
	let shop = $state<string>('all');
	let group = $state<string>('all');
	let minPct = $state(0);
	let sort = $state<'discount' | 'price' | 'title'>('discount');

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
	<h1 class="text-xl font-bold text-slate-100">Все скидки</h1>
	<span class="text-sm text-slate-400">
		<span class="font-semibold text-amber-400">{filtered.length}</span>
		из {dashboard.deals.length}
	</span>
</div>

<!-- Фильтры -->
<div class="mb-6 space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
	<div class="flex flex-wrap gap-3">
		<label class="relative min-w-[220px] flex-1">
			<Search class="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-slate-500" />
			<input
				type="search"
				bind:value={query}
				placeholder="Поиск по названию…"
				class="w-full rounded-lg border border-slate-700 bg-slate-800 py-2 pr-3 pl-9 text-sm text-slate-100 placeholder:text-slate-500 focus:border-amber-500 focus:outline-none"
			/>
		</label>

		<select
			bind:value={sort}
			class="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-amber-500 focus:outline-none"
		>
			<option value="discount">По скидке</option>
			<option value="price">По цене</option>
			<option value="title">По названию</option>
		</select>

		{#if hasFilters}
			<button
				onclick={reset}
				class="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200"
			>
				<X class="h-4 w-4" /> Сбросить
			</button>
		{/if}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<span class="text-xs text-slate-500">Магазин:</span>
		{#each shops as name (name)}
			<button
				onclick={() => (shop = name)}
				class="rounded-full px-3 py-1 text-xs transition-colors {shop === name
					? 'bg-amber-500 text-slate-950'
					: 'bg-slate-800 text-slate-400 hover:text-slate-200'}"
			>
				{name === 'all' ? 'все' : shopLabel(name)}
			</button>
		{/each}
	</div>

	<div class="flex flex-wrap items-center gap-2">
		<span class="text-xs text-slate-500">Группа:</span>
		{#each groups as key (key)}
			<button
				onclick={() => (group = key)}
				class="rounded-full px-3 py-1 text-xs transition-colors {group === key
					? 'bg-amber-500 text-slate-950'
					: 'bg-slate-800 text-slate-400 hover:text-slate-200'}"
			>
				{key === 'all' ? 'все' : groupLabel(key)}
			</button>
		{/each}
	</div>

	<div class="flex items-center gap-3">
		<span class="text-xs text-slate-500">Скидка от</span>
		<input
			type="range"
			min="0"
			max="90"
			step="5"
			bind:value={minPct}
			class="h-1.5 w-40 cursor-pointer accent-amber-500"
		/>
		<span class="w-10 text-sm font-medium text-amber-400">−{minPct}%</span>
	</div>
</div>

{#if filtered.length}
	<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
		{#each filtered as deal (deal.product.shop + deal.product.sku)}
			<DealCard {deal} />
		{/each}
	</div>
{:else}
	<div class="rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-center">
		<p class="text-slate-400">Ничего не нашлось</p>
		{#if hasFilters}
			<button onclick={reset} class="mt-3 text-sm text-amber-400 hover:text-amber-300">
				Сбросить фильтры
			</button>
		{/if}
	</div>
{/if}