<script lang="ts">
	import { dashboard } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import { shopLabel, groupLabel } from '$lib/utils/format';
	import { Trophy, Star, TrendingUp, ShieldCheck, ArrowRight } from '@lucide/svelte';
	import { base } from '$app/paths';

	let picks = $derived(dashboard.deals.filter(d => d.is_pick));
	let fair = $derived(dashboard.deals.filter(d => d.badges?.includes('Честная скидка') && !d.is_pick));
	let byValue = $derived([...dashboard.deals].sort((a,b) => (b.value_score ?? 0) - (a.value_score ?? 0)).slice(0, 12));
	let byGroup = $derived.by(() => {
		const m = new Map<string, typeof dashboard.deals>();
		for (const d of dashboard.deals) {
			const k = d.product.group ?? 'other';
			if (!m.has(k)) m.set(k, []);
			m.get(k)!.push(d);
		}
		return [...m.entries()].map(([k, v]) => ({ key: k, best: [...v].sort((a,b)=>(b.value_score??0)-(a.value_score??0))[0], count: v.length }));
	});
</script>

<svelte:head><title>Топ-выбор — skidki</title></svelte:head>

<div class="mb-6">
	<p class="page-eyebrow">Выбор ИС</p>
	<h1 class="page-heading">Топ <em>лучших</em> покупок</h1>
	<p class="page-description">
		«Выбор ИС» — честная скидка ≥18%, value ≥78, цена ≥20k, в наличии. «Честная скидка» — подтверждена историей ≥3 дней.
		Оценка считается при экспорте (см. docs/RANKING_2026.md).
	</p>
</div>

{#if picks.length}
	<section class="mb-8">
		<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight mb-3" style="color:var(--ink)"><Trophy size={18} /> Выбор ИС · {picks.length}</h2>
		<div class="product-grid">
			{#each picks as deal (deal.product.shop + deal.product.sku)}<DealCard {deal} />{/each}
		</div>
	</section>
{:else}
	<div class="rounded-2xl p-8 text-center mb-8" style="background:white; border:1px solid var(--line); color:var(--ink-4)">Пока нет «Выбора ИС» — наберётся история и появятся честные скидки.</div>
{/if}

<section class="mb-8">
	<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight mb-3" style="color:var(--ink)"><ShieldCheck size={18} /> Честная скидка</h2>
	<p class="text-xs mb-3" style="color:var(--ink-4)">Подтверждена медианой 14 дней (≥3 дня истории). Исключает рисованные зачёркивания.</p>
	{#if fair.length}
		<div class="product-grid">
			{#each fair.slice(0, 8) as deal (deal.product.shop + deal.product.sku)}<DealCard {deal} />{/each}
		</div>
		{#if fair.length > 8}<a href="{base}/deals" class="section-link mt-3">Все честные · {fair.length} <ArrowRight size={14} /></a>{/if}
	{:else}
		<p class="text-sm" style="color:var(--ink-4)">Пока нет.</p>
	{/if}
</section>

<section class="mb-8">
	<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight mb-3" style="color:var(--ink)"><Star size={18} /> Топ по ценности (value)</h2>
	<div class="product-grid">
		{#each byValue as deal, i (deal.product.shop + deal.product.sku)}<DealCard {deal} rank={i+1} />{/each}
	</div>
</section>

<section>
	<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight mb-3" style="color:var(--ink)"><TrendingUp size={18} /> Лучшее по группам</h2>
	<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
		{#each byGroup as row (row.key)}
			<a href="{base}/deals?group={row.key}" class="rounded-2xl p-4 flex items-center justify-between gap-3 hover:shadow-[var(--shadow)] transition-shadow" style="background:white; border:1px solid var(--line)">
				<span class="text-sm font-medium" style="color:var(--ink-2)">{groupLabel(row.key)}</span>
				<span class="text-xs px-2.5 py-1 rounded-full font-mono font-bold" style="background:var(--paper-2); color:var(--ink)">{row.count} · {row.best.value_score ?? '—'}</span>
			</a>
		{/each}
	</div>
</section>
