<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import { favorites } from '$lib/stores/favorites.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import { Heart, Trash2, ArrowRight, ShoppingBag } from '@lucide/svelte';

	let favDeals = $derived(dashboard.deals.filter(d => favorites.has(`${d.product.shop}:${d.product.sku}`)));
	let missing = $derived(Math.max(0, favorites.count - favDeals.length));

	function copyList() {
		const urls = favDeals.map(d => d.product.url).join('\n');
		navigator.clipboard.writeText(urls).catch(() => {});
	}
</script>

<svelte:head><title>Избранное — skidki</title></svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Отложено</p>
		<h1 class="page-heading">Избранное <em>· {favorites.count}</em></h1>
		<p class="page-description">Отслеживай интересное. Хранится в браузере — без аккаунта.</p>
	</div>
	{#if favDeals.length}
		<div class="flex gap-2">
			<button onclick={copyList} class="h-10 px-4 rounded-full text-sm font-semibold" style="background:var(--surface); border:1px solid var(--line); color:var(--ink-2)">Копировать ссылки</button>
			<button onclick={() => favorites.clear()} class="h-10 px-4 rounded-full text-sm font-semibold inline-flex items-center gap-1.5" style="background:var(--accent-2); border:1px solid color-mix(in srgb, var(--accent) 18%, transparent); color:var(--accent)"><Trash2 size={14} /> Очистить</button>
		</div>
	{/if}
</div>

{#if !favorites.ready}
	<p class="text-sm" style="color:var(--ink-4)">Загрузка…</p>
{:else if favDeals.length === 0}
	<div class="rounded-2xl p-10 text-center" style="background:var(--surface); border:1px solid var(--line)">
		<div class="mx-auto w-12 h-12 rounded-2xl grid place-items-center mb-4" style="background:var(--paper-2); border:1px solid var(--line)"><Heart size={20} style="color:var(--ink-3)" /></div>
		<p class="font-semibold" style="color:var(--ink)">Пока пусто</p>
		<p class="text-sm mt-1" style="color:var(--ink-4)">Нажимай <Heart size={12} class="inline" /> на карточках — они появятся здесь.</p>
		<a href="{base}/deals" class="inline-flex items-center gap-1.5 mt-4 text-sm font-semibold" style="color:var(--ink)">В каталог <ArrowRight size={14} /></a>
	</div>
{:else}
	{#if missing}
		<p class="text-xs mb-3 px-3 py-2 rounded-xl" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink-4)">
			<ShoppingBag size={12} class="inline mr-1" />{missing} {missing === 1 ? 'товар из избранного сейчас вне топа' : 'товаров из избранного сейчас вне топа'} — появятся, когда вернётся скидка.
		</p>
	{/if}
	<div class="product-grid">
		{#each favDeals as deal (deal.product.shop + deal.product.sku)}
			<DealCard {deal} />
		{/each}
	</div>
{/if}
