<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import { compare } from '$lib/stores/compare.svelte';
	import { formatPrice, shopLabel, formatPct } from '$lib/utils/format';
	import { Scale, Trash2, ArrowRight, ExternalLink } from '@lucide/svelte';

	let items = $derived(
		compare.ids
			.map(id => dashboard.deals.find(d => `${d.product.shop}:${d.product.sku}` === id))
			.filter(Boolean) as typeof dashboard.deals
	);
	let missing = $derived(compare.count - items.length);
</script>

<svelte:head><title>Сравнение — skidki</title></svelte:head>

<div class="mb-6">
	<p class="page-eyebrow">Сравнение</p>
	<h1 class="page-heading">Сравнение <em>· {compare.count}/4</em></h1>
	<p class="page-description">До 4 товаров. Добавляй через кнопку «Сравнение» на карточке.</p>
</div>

{#if !compare.ready}
	<p class="text-sm" style="color:var(--ink-4)">Загрузка…</p>
{:else if items.length === 0}
	<div class="rounded-2xl p-10 text-center" style="background:var(--surface); border:1px solid var(--line)">
		<div class="mx-auto w-12 h-12 rounded-2xl grid place-items-center mb-4" style="background:var(--paper-2); border:1px solid var(--line)"><Scale size={20} style="color:var(--ink-3)" /></div>
		<p class="font-semibold" style="color:var(--ink)">Пусто</p>
		<p class="text-sm mt-1" style="color:var(--ink-4)">Добавь товары из каталога или топа.</p>
		<a href="{base}/deals" class="inline-flex items-center gap-1.5 mt-4 text-sm font-semibold" style="color:var(--ink)">В каталог <ArrowRight size={14} /></a>
	</div>
{:else}
	<div class="flex gap-2 mb-4">
		<button onclick={() => compare.clear()} class="h-9 px-4 rounded-full text-sm font-semibold inline-flex items-center gap-1.5" style="background:var(--surface); border:1px solid var(--line); color:var(--ink-3)"><Trash2 size={14} /> Очистить</button>
		{#if missing}<span class="text-xs px-3 py-2 rounded-full" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink-4)">{missing} вне топа — вернутся со скидкой</span>{/if}
	</div>

	<div class="overflow-x-auto rounded-2xl" style="background:var(--surface); border:1px solid var(--line)">
		<table class="w-full text-sm" style="min-width:640px">
			<thead>
				<tr style="border-bottom:1px solid var(--line); color:var(--ink-4)" class="text-xs">
					<th class="text-left p-3 font-semibold">Параметр</th>
					{#each items as d (d.product.shop + d.product.sku)}<th class="text-left p-3 font-semibold">{shopLabel(d.product.shop)}</th>{/each}
				</tr>
			</thead>
			<tbody>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Товар</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3"><a href="{base}/item?shop={d.product.shop}&sku={d.product.sku}" class="font-medium hover:underline" style="color:var(--ink)">{d.product.title}</a><div class="text-xs" style="color:var(--ink-4)">{d.product.brand ?? ''}</div></td>{/each}</tr>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Цена</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3 font-mono font-bold" style="color:var(--ink)">{formatPrice(d.product.price)}</td>{/each}</tr>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Скидка магаз.</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3 font-mono" style="color:var(--accent)">{d.drop_pct != null ? formatPct(d.drop_pct) : '—'}</td>{/each}</tr>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Честная</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3 font-mono" style="color:var(--success)">{d.fair_discount != null ? d.fair_discount + '%' : '—'}</td>{/each}</tr>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Value</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3 font-mono font-bold">{d.value_score ?? '—'}</td>{/each}</tr>
				<tr style="border-bottom:1px solid var(--paper-2)"><td class="p-3 font-medium" style="color:var(--ink-3)">Бейджи</td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3 text-xs">{(d.badges ?? []).join(' · ') || '—'}</td>{/each}</tr>
				<tr><td class="p-3"></td>{#each items as d (d.product.shop + d.product.sku)}<td class="p-3"><a href={d.product.url} target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-xs font-semibold" style="color:var(--ink-3)">В магазин <ExternalLink size={12} /></a></td>{/each}</tr>
			</tbody>
		</table>
	</div>
{/if}
