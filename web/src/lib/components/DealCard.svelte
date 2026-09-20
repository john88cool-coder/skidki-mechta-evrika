<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import type { Deal } from '$lib/types';
	import { dashboard, priceHistory } from '$lib/stores/data.svelte';
	import { formatPrice, formatPct, shopLabel, formatDate } from '$lib/utils/format';
	import { recentPrices, formatChange } from '$lib/utils/history';
	import { ExternalLink, ArrowUpRight, ImageOff, Clock3 } from '@lucide/svelte';

	interface Props { deal: Deal; rank?: number; returnTo?: string }
	let { deal, rank = 0, returnTo }: Props = $props();
	let product = $derived(deal.product);
	let hasDiscount = $derived(!!product.old_price && product.old_price > product.price);
	let discount = $derived(hasDiscount ? (1 - product.price / product.old_price!) * 100 : null);
	let historyHref = $derived(`${base}/item?shop=${encodeURIComponent(product.shop)}&sku=${encodeURIComponent(product.sku)}&from=${encodeURIComponent(returnTo ?? page.url.pathname + page.url.search)}`);
	let failedImage = $state('');
	let history = $derived(priceHistory.data?.history[`${product.shop}:${product.sku}`]);
	let prices = $derived(recentPrices(history?.recent_points ?? history?.points ?? []).reverse());
	let source = $derived(dashboard.shops.find(s => s.name === product.shop));
	let differentSnapshot = $derived(prices.length > 0 && prices[0].price !== product.price);
</script>

<article class="product-card">
	<div class="product-visual">
		<a href={historyHref} class="product-photo" aria-label={`История цены: ${product.title}`}>
			{#if product.image && failedImage !== product.image}
				<img src={product.image} alt={product.title} loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror={() => (failedImage = product.image ?? '')} />
			{:else}
				<div class="image-placeholder"><ImageOff size={30} /><span>Фото недоступно</span></div>
			{/if}
		</a>
		{#if discount !== null}<span class="discount-label">{formatPct(discount)} <span>в магазине</span></span>{/if}
		{#if rank > 0}<span class="rank-label">{String(rank).padStart(2, '0')}</span>{/if}
	</div>
	<div class="product-body">
		<div class="product-meta"><span>{shopLabel(product.shop)}</span><span class:unavailable={!product.in_stock}>{product.in_stock ? 'В наличии' : 'Нет в наличии'}</span></div>
		<h3><a href={historyHref}>{product.title}</a></h3>
		<div class="product-price"><strong>{formatPrice(product.price)}</strong>{#if hasDiscount}<del aria-label="Старая цена магазина">{formatPrice(product.old_price!)}</del>{/if}</div>
		{#if source && source.status !== 'ok'}<p class="source-warning"><Clock3 size={12} /> {source.status === 'warning' ? 'Данные магазина устарели' : 'Источник требует проверки'}</p>{/if}
		<section class="card-history" aria-label={`Последние цены: ${product.title}`}>
			<div class="history-heading"><h4>История цены</h4><span>Последние {prices.length || '—'}</span></div>
			{#if priceHistory.loading}<p class="history-message" role="status">Загружаем наблюдения…</p>
			{:else if priceHistory.error}<p class="history-message">История временно недоступна. <button onclick={() => priceHistory.load()}>Повторить</button></p>
			{:else if prices.length}
				<table><caption class="sr-only">От новых к старым. Изменение относительно предыдущего наблюдения.</caption><thead><tr><th scope="col">Дата</th><th scope="col">Цена, ₸</th><th scope="col">Изм.</th></tr></thead><tbody>
				{#each prices as point, index}
					<tr class:latest={index === 0}><td><time datetime={point.date} title={point.date}>{formatDate(point.date)}</time></td><td>{formatPrice(point.price)}</td><td class:price-down={point.change !== null && point.change < 0} class:price-up={point.change !== null && point.change > 0}>{formatChange(point.change)}</td></tr>
				{/each}
				</tbody></table>
				<p class="history-note">{prices.length === 1 ? 'Первое наблюдение. Изменения появятся позже.' : '% к предыдущей записи · новые сверху'}</p>
				{#if differentSnapshot}<p class="source-warning">История и текущая цена из разных срезов.</p>{/if}
			{:else}<p class="history-message">Наблюдения ещё не накоплены.</p>{/if}
		</section>
		<div class="product-actions"><a class="history-action" href={historyHref}>Вся история <ArrowUpRight size={15} /></a><a class="shop-action" href={product.url} target="_blank" rel="noopener noreferrer">В магазин <ExternalLink size={13} /></a></div>
	</div>
</article>
