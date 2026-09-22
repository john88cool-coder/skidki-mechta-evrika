<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import type { Deal } from '$lib/types';
	import { dashboard, priceHistory } from '$lib/stores/data.svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import { formatPrice, formatPct, shopLabel, formatDate } from '$lib/utils/format';
	import { recentPrices, formatChange } from '$lib/utils/history';
	import { ExternalLink, ArrowUpRight, ImageOff, Clock3, Heart, Share2, Check, Scale } from '@lucide/svelte';
	import { compare, cmpId } from '$lib/stores/compare.svelte';
	import { badgeTone } from '$lib/utils/format';

	interface Props { deal: Deal; rank?: number; returnTo?: string }
	let { deal, rank = 0, returnTo }: Props = $props();
	let product = $derived(deal.product);
	let hasDiscount = $derived(!!product.old_price && product.old_price > product.price);
	let discount = $derived(hasDiscount ? (1 - product.price / product.old_price!) * 100 : null);
	let savings = $derived(hasDiscount ? product.old_price! - product.price : 0);
	let historyHref = $derived(`${base}/item?shop=${encodeURIComponent(product.shop)}&sku=${encodeURIComponent(product.sku)}&from=${encodeURIComponent(returnTo ?? page.url.pathname + page.url.search)}`);
	let id = $derived(favId(product.shop, product.sku));
	let isFav = $derived(favorites.has(id));
	let failedImage = $state('');
	let copied = $state(false);
	let cmp = $derived(compare.has(cmpId(product.shop, product.sku)));
	let history = $derived(priceHistory.data?.history[`${product.shop}:${product.sku}`]);
	let prices = $derived(recentPrices(history?.recent_points ?? history?.points ?? []).reverse());
	let source = $derived(dashboard.shops.find(s => s.name === product.shop));
	let differentSnapshot = $derived(prices.length > 0 && prices[0].price !== product.price);

	async function share() {
		const url = `${location.origin}${historyHref}`;
		try {
			if (navigator.share) { await navigator.share({ title: product.title, url }); return; }
		} catch {}
		try { await navigator.clipboard.writeText(url); } catch { /* fallback below */ }
		copied = true; setTimeout(() => (copied = false), 1600);
	}
</script>

<article class="product-card">
	<div class="product-visual">
		<a href={historyHref} class="product-photo" aria-label={`История цены: ${product.title}`}>
			{#if product.image && failedImage !== product.image}
				<img src={product.image} alt={product.title} loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror={() => (failedImage = product.image ?? '')} />
			{:else}
				<div class="image-placeholder"><ImageOff size={28} /><span>Фото недоступно</span></div>
			{/if}
		</a>
		{#if discount !== null}<span class="discount-pill">{formatPct(discount)} <small>скидка</small></span>{/if}
		{#if rank > 0}<span class="rank-label">#{String(rank).padStart(2,'0')}</span>{/if}
		<button
			class="fav-btn"
			class:faved={isFav}
			onclick={() => favorites.toggle(id)}
			aria-label={isFav ? 'Убрать из избранного' : 'В избранное'}
			title={isFav ? 'В избранном' : 'В избранное'}
		><Heart size={16} fill={isFav ? 'currentColor' : 'none'} /></button>
	</div>
	<div class="product-body">
		<div class="product-meta">
			<span class="meta-shop">{shopLabel(product.shop)}</span>
			<span class="meta-stock" class:bad={!product.in_stock}>{product.in_stock ? 'В наличии' : 'Нет в наличии'}</span>
		</div>
		{#if deal.badges?.length || deal.is_pick || product.badges?.length}
			<div class="badge-row">
				{#each (deal.badges ?? product.badges ?? []) as b (b)}
					<span class="badge badge-{badgeTone(b)}">{b}</span>
				{/each}
				{#if deal.fair_discount != null}<span class="badge badge-fair">честно {deal.fair_discount}%</span>{/if}
				{#if deal.value_score != null}<span class="badge badge-score" title="Value score">{deal.value_score}</span>{/if}
			</div>
		{/if}
		<h3><a href={historyHref}>{product.title}</a></h3>
		{#if product.brand}<p class="text-xs mt-1" style="color:var(--ink-4)">{product.brand}{product.category ? ` · ${product.category}` : ''}</p>{/if}
		<div class="product-price">
			<strong>{formatPrice(product.price)}</strong>
			{#if hasDiscount}<del>{formatPrice(product.old_price!)}</del><span class="price-save">−{formatPrice(savings)}</span>{/if}
		</div>
		{#if source && source.status !== 'ok'}<p class="source-warning"><Clock3 size={12} /> {source.status === 'warning' ? 'Данные магазина устарели' : 'Источник требует проверки'}</p>{/if}
		<section class="card-history" aria-label={`Последние цены: ${product.title}`}>
			<div class="history-heading"><h4>История</h4><span>{prices.length ? `${prices.length} точек` : '—'}</span></div>
			{#if priceHistory.loading}<p class="history-message" role="status">Загружаем наблюдения…</p>
			{:else if priceHistory.error}<p class="history-message">История временно недоступна. <button onclick={() => priceHistory.load()}>Повторить</button></p>
			{:else if prices.length}
				<table><caption class="sr-only">От новых к старым. Изменение к предыдущему наблюдению.</caption><thead><tr><th scope="col">Дата</th><th scope="col">Цена</th><th scope="col">Изм.</th></tr></thead><tbody>
				{#each prices as point, index}
					<tr class:latest={index === 0}><td><time datetime={point.date} title={point.date}>{formatDate(point.date)}</time></td><td>{formatPrice(point.price)}</td><td class:price-down={point.change !== null && point.change < 0} class:price-up={point.change !== null && point.change > 0}>{formatChange(point.change)}</td></tr>
				{/each}
				</tbody></table>
				<p class="history-note">{prices.length === 1 ? 'Первое наблюдение — изменения появятся позже.' : '% к предыдущей записи · новые сверху'}</p>
				{#if differentSnapshot}<p class="source-warning">История и текущая цена из разных срезов.</p>{/if}
			{:else}<p class="history-message">Наблюдения ещё не накоплены.</p>{/if}
		</section>
		<div class="product-actions">
			<a class="history-action" href={historyHref}>История <ArrowUpRight size={14} /></a>
			<a class="shop-action" href={product.url} target="_blank" rel="noopener noreferrer">В магазин <ExternalLink size={13} /></a>
			<button class="shop-action !px-2.5" class:compare-on={cmp} onclick={() => compare.toggle(cmpId(product.shop, product.sku))} title={cmp ? "Убрать из сравнения" : "В сравнение"} aria-label="Сравнение"><Scale size={14} /></button>
			<button class="shop-action !px-2.5" onclick={share} aria-label="Поделиться" title="Поделиться">
				{#if copied}<Check size={14} />{:else}<Share2 size={14} />{/if}
			</button>
		</div>
	</div>
</article>

<style>
	.fav-btn {
		position: absolute; top: 14px; right: 14px;
		width: 32px; height: 32px; border-radius: 999px;
		display: grid; place-items: center;
		background: rgba(255,255,255,0.92); backdrop-filter: blur(8px);
		border: 1px solid var(--line); color: var(--ink-3);
		transition: all .15s;
	}
	.fav-btn:hover { background: white; color: var(--ink); }
	.fav-btn.faved { background: var(--accent); border-color: var(--accent); color: white; }
	/* when rank is also shown, stack fav below it */
	.product-visual:has(.rank-label) .fav-btn { top: 46px; }
	.compare-on { background: var(--ink) !important; color: white !important; border-color: var(--ink) !important; }
	.badge-row { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
	.badge { font-size:10px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; padding:3px 7px; border-radius:999px; border:1px solid var(--line); }
	.badge-pick { background: var(--ink); color:white; border-color: var(--ink); }
	.badge-fair { background: var(--success-bg); color: var(--success); border-color: color-mix(in srgb, var(--success) 18%, transparent); }
	.badge-brand { background: #fff7e6; color:#9a6a0a; border-color:#ffe2a8; }
	.badge-warn { background: var(--accent-2); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 18%, transparent); }
	.badge-score { background: var(--paper-2); color: var(--ink-2); }
</style>
