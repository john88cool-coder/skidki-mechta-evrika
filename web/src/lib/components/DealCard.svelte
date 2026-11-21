<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import type { Deal } from '$lib/types';
	import { dashboard, priceHistory } from '$lib/stores/data.svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import { formatPrice, formatPct, shopLabel } from '$lib/utils/format';
	import { verdictOf } from '$lib/utils/verdict';
	import { ExternalLink, ImageOff, Clock3, Heart } from '@lucide/svelte';
	import VerdictChip from './VerdictChip.svelte';
	import Sparkline from './Sparkline.svelte';

	/**
	 * Карточка товара в списках. Вся карточка — ссылка на страницу товара;
	 * поверх неё — только «в избранное» и «в магазин». Мини-график цены виден сразу:
	 * история — главное, чем панель отличается от витрины магазина.
	 */
	interface Props { deal: Deal; returnTo?: string }
	let { deal, returnTo }: Props = $props();
	let product = $derived(deal.product);
	let hasDiscount = $derived(!!product.old_price && product.old_price > product.price);
	let discount = $derived(hasDiscount ? (1 - product.price / product.old_price!) * 100 : null);
	let verdict = $derived(verdictOf(deal));
	// «Обычная цена» — честная база из среза; показываем, когда она выше текущей.
	let usual = $derived(deal.base_price && deal.base_price > product.price * 1.01 ? deal.base_price : null);
	let itemHref = $derived(`${base}/item?shop=${encodeURIComponent(product.shop)}&sku=${encodeURIComponent(product.sku)}&from=${encodeURIComponent(returnTo ?? page.url.pathname + page.url.search)}`);
	let id = $derived(favId(product.shop, product.sku));
	let isFav = $derived(favorites.has(id));
	let failedImage = $state('');
	let points = $derived(priceHistory.data?.history[`${product.shop}:${product.sku}`]?.points ?? []);
	let source = $derived(dashboard.shops.find((s) => s.name === product.shop));
	// Пояснение — только там, где вердикт расходится с ценником.
	let hint = $derived(
		verdict.kind === 'inflated' || verdict.kind === 'pumped' || verdict.kind === 'painted' ? verdict.hint : null
	);
</script>

<article class="deal-card">
	<div class="dc-visual">
		{#if product.image && failedImage !== product.image}
			<img src={product.image} alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror={() => (failedImage = product.image ?? '')} />
		{:else}
			<span class="dc-noimg"><ImageOff size={22} /></span>
		{/if}
		{#if verdict.real}
			<span class="dc-pill real" title={verdict.hint}>-{Math.round(verdict.real)}%<small>реально</small></span>
		{:else if discount !== null}
			<span class="dc-pill" class:painted={verdict.kind === 'painted'} title={verdict.hint}>{formatPct(discount)}<small>{verdict.kind === 'painted' ? 'на ценнике' : 'скидка'}</small></span>
		{/if}
		<button
			class="dc-fav"
			class:on={isFav}
			onclick={() => favorites.toggle(id, product)}
			aria-pressed={isFav}
			aria-label={isFav ? `Убрать из избранного: ${product.title}` : `В избранное: ${product.title}`}
		><Heart size={16} fill={isFav ? 'currentColor' : 'none'} /></button>
	</div>

	<div class="dc-body">
		<div class="dc-meta">
			<span class="dc-shop">{shopLabel(product.shop)}</span>
			<VerdictChip {verdict} />
			{#if !product.in_stock}<span class="dc-out">Нет в наличии</span>{/if}
		</div>
		<h3><a class="dc-link" href={itemHref}>{product.title}</a></h3>
		<div class="dc-price">
			<strong>{formatPrice(product.price)}</strong>
			{#if usual}
				<span>обычно {formatPrice(usual)}</span>
			{:else if hasDiscount}
				<del title="Зачёркнутая цена магазина">{formatPrice(product.old_price!)}</del>
			{/if}
		</div>
		{#if hint}<p class="dc-hint {verdict.kind}">{hint}</p>{/if}
		{#if source && source.status !== 'ok'}
			<p class="dc-stale"><Clock3 size={13} /> {source.status === 'warning' ? 'Данные магазина устарели' : 'Источник требует проверки'}</p>
		{/if}
		<div class="dc-foot">
			<div class="dc-spark">
				{#if points.length > 1}
					<Sparkline {points} label="Цена {product.title}" />
				{:else}
					<span class="dc-nohist">{priceHistory.loading ? 'Загружаем историю…' : 'История копится'}</span>
				{/if}
			</div>
			{#if product.url && product.url !== '#'}
				<a class="dc-store" href={product.url} target="_blank" rel="noopener noreferrer" aria-label="Открыть в магазине {shopLabel(product.shop)}: {product.title}" title="В магазин"><ExternalLink size={16} /></a>
			{/if}
		</div>
	</div>
</article>

<style>
	.deal-card {
		position: relative;
		display: flex;
		flex-direction: column;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		overflow: hidden;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.deal-card:hover { border-color: var(--line-2); box-shadow: var(--shadow-lg); }
	.dc-visual {
		position: relative;
		height: 168px;
		margin: 8px 8px 0;
		border-radius: 12px;
		background: #ffffff;
		display: grid;
		place-items: center;
		overflow: hidden;
	}
	.dc-visual img { width: 100%; height: 100%; object-fit: contain; padding: 14px; }
	.dc-noimg { color: #8a9a93; }
	.dc-pill {
		position: absolute; top: 8px; left: 8px;
		display: inline-flex; align-items: baseline; gap: 4px;
		padding: 5px 9px; border-radius: 999px;
		background: var(--accent); color: #fff;
		font-family: var(--font-mono); font-size: 13px; font-weight: 700; line-height: 1;
	}
	.dc-pill small { font-family: var(--font-sans); font-size: 10px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
	.dc-pill.real { background: var(--success); }
	:global(html[data-theme='dark']) .dc-pill.real { color: #06130d; }
	.dc-pill.painted { background: #6f6a63; text-decoration: line-through; }
	.dc-pill.painted small { text-decoration: none; }
	.dc-fav {
		position: absolute; top: 6px; right: 6px; z-index: 2;
		width: 40px; height: 40px; border-radius: 999px;
		display: grid; place-items: center;
		background: rgba(255, 255, 255, 0.92); color: #4f6059;
		border: 1px solid rgba(14, 26, 21, 0.1);
	}
	.dc-fav:hover { color: #0e1a15; }
	.dc-fav.on { background: var(--accent); border-color: var(--accent); color: #fff; }
	.dc-body { display: flex; flex-direction: column; flex: 1; padding: 12px 14px 12px; min-width: 0; }
	.dc-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; }
	.dc-shop { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-2); }
	.dc-out { font-size: 12px; font-weight: 600; color: var(--bad); }
	.deal-card h3 {
		margin-top: 8px;
		font-size: 14px; line-height: 1.4; font-weight: 600; letter-spacing: -0.01em;
		display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
		min-height: calc(14px * 1.4 * 2);
	}
	.dc-link { color: var(--ink); text-decoration: none; }
	/* Вся карточка кликабельна: ссылка растянута поверх, кнопки — над ней (z-index 2). */
	.dc-link::after { content: ''; position: absolute; inset: 0; z-index: 1; }
	.deal-card:hover .dc-link { color: var(--accent); }
	.dc-link:focus-visible { outline: none; }
	.deal-card:has(.dc-link:focus-visible) { outline: 2px solid var(--ink); outline-offset: 2px; }
	.dc-price { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; margin-top: 8px; }
	.dc-price strong { font-family: var(--font-mono); font-size: 20px; font-weight: 700; letter-spacing: -0.04em; color: var(--ink); }
	.dc-price span, .dc-price del { font-family: var(--font-mono); font-size: 13px; color: var(--ink-3); }
	.dc-hint {
		margin-top: 8px; padding: 6px 9px; border-radius: var(--radius-xs);
		font-size: 12px; font-weight: 600; line-height: 1.35;
		border: 1px solid transparent;
		display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
	}
	.dc-hint.inflated, .dc-hint.pumped { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-line); }
	.dc-hint.painted { background: var(--bad-bg); color: var(--bad); border-color: var(--bad-line); }
	.dc-stale {
		display: flex; align-items: center; gap: 5px; margin-top: 8px;
		font-size: 12px; color: var(--warn);
	}
	.dc-foot { display: flex; align-items: center; gap: 10px; margin-top: auto; padding-top: 10px; }
	.dc-spark { flex: 1; min-width: 0; height: 40px; display: flex; align-items: center; }
	.dc-nohist { font-size: 12px; color: var(--ink-4); }
	.dc-store {
		position: relative; z-index: 2; flex-shrink: 0;
		width: 40px; height: 40px; border-radius: 999px;
		display: grid; place-items: center;
		border: 1px solid var(--line); color: var(--ink-2); background: var(--surface);
	}
	.dc-store:hover { border-color: var(--ink); color: var(--ink); }

	/* Телефон: горизонтальная карточка — фото слева, три-четыре карточки на экран. */
	@media (max-width: 640px) {
		.deal-card { flex-direction: row; }
		.dc-visual { width: 104px; height: auto; min-height: 128px; margin: 8px 0 8px 8px; flex-shrink: 0; }
		.dc-visual img { padding: 8px; }
		.dc-pill { top: auto; bottom: 6px; left: 6px; padding: 4px 7px; font-size: 12px; }
		.dc-pill small { display: none; }
		.dc-fav { top: 4px; right: 4px; }
		.dc-body { padding: 10px 12px; }
		.deal-card h3 { margin-top: 6px; min-height: 0; }
		.dc-price { margin-top: 6px; }
		.dc-price strong { font-size: 18px; }
		.dc-hint { margin-top: 6px; }
		.dc-foot { padding-top: 6px; }
		.dc-spark, :global(.dc-spark .spark) { height: 32px; }
	}
</style>
