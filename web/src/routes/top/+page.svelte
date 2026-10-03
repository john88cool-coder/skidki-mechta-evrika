<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import { shopLabel, groupLabel, formatPrice } from '$lib/utils/format';
	import { verdictOf, realRank } from '$lib/utils/verdict';
	import { Trophy, Ban, LayoutGrid, ArrowRight } from '@lucide/svelte';

	let real = $derived(
		dashboard.deals
			.filter((d) => { const k = verdictOf(d).kind; return k === 'honest' || k === 'inflated'; })
			.sort((a, b) => realRank(b) - realRank(a))
	);
	/** Лучшее реальное снижение в каждой группе — «что брать» по разделам. */
	let perGroup = $derived.by(() => {
		const best = new Map<string, (typeof real)[number]>();
		for (const d of real) {
			const key = d.product.group ?? 'other';
			if (!best.has(key)) best.set(key, d);
		}
		return [...best.entries()];
	});
	/** Самый большой разрыв между ценником и реальностью. */
	let lies = $derived(
		dashboard.deals
			.filter((d) => { const v = verdictOf(d); return v.kind === 'painted' || v.kind === 'inflated'; })
			.map((d) => { const v = verdictOf(d); return { d, gap: (v.claimed ?? 0) - (v.real ?? 0) }; })
			.sort((a, b) => b.gap - a.gap)
			.slice(0, 8)
	);
</script>

<svelte:head><title>Лучшие покупки — skidki</title></svelte:head>

<div class="mb-8">
	<p class="page-eyebrow">Топ</p>
	<h1 class="page-heading">Лучшие <em>покупки</em></h1>
	<p class="page-description">
		Только то, что подешевело по собственной истории цены, — от самого сильного снижения. Процент на ценнике здесь роли не играет.
	</p>
</div>

<section class="block">
	<div class="section-head">
		<h2><Trophy size={20} class="inline -mt-1 mr-1" /> Сильнее всего <i>подешевело</i></h2>
		<a href="{base}/deals?v=real" class="section-link">Все {real.length} <ArrowRight size={14} /></a>
	</div>
	{#if real.length}
		<div class="product-grid">
			{#each real.slice(0, 12) as deal, i (deal.product.shop + deal.product.sku)}<DealCard {deal} rank={i + 1} />{/each}
		</div>
	{:else}
		<div class="empty-state"><p style="color:var(--ink-3)">Подтверждённых снижений пока нет — нужна история хотя бы за 3 дня.</p></div>
	{/if}
</section>

{#if perGroup.length}
	<section class="block">
		<div class="section-head"><h2><LayoutGrid size={20} class="inline -mt-1 mr-1" /> Лучшее <i>в каждой группе</i></h2></div>
		<div class="group-picks">
			{#each perGroup as [key, d] (key)}
				<a class="group-pick" href="{base}/item?shop={encodeURIComponent(d.product.shop)}&sku={encodeURIComponent(d.product.sku)}">
					<span class="gp-group">{groupLabel(key)}</span>
					<span class="gp-thumb">{#if d.product.image}<img src={d.product.image} alt="" loading="lazy" referrerpolicy="no-referrer" />{/if}</span>
					<span class="gp-title">{d.product.title}</span>
					<span class="gp-price"><b>{formatPrice(d.product.price)}</b><em>−{Math.round(verdictOf(d).real ?? 0)}%</em></span>
					<span class="gp-shop">{shopLabel(d.product.shop)}{d.base_price ? ` · обычно ${formatPrice(d.base_price)}` : ''}</span>
				</a>
			{/each}
		</div>
	</section>
{/if}

{#if lies.length}
	<section class="block">
		<div class="section-head">
			<h2><Ban size={20} class="inline -mt-1 mr-1" /> Ценник <i>против истории</i></h2>
			<a href="{base}/deals?v=painted" class="section-link">Все нарисованные <ArrowRight size={14} /></a>
		</div>
		<p class="block-lead">Самый большой разрыв между процентом на ценнике и реальным снижением цены.</p>
		<div class="painted-list">
			{#each lies as { d, gap } (d.product.shop + d.product.sku)}
				<a class="painted-row" href="{base}/item?shop={encodeURIComponent(d.product.shop)}&sku={encodeURIComponent(d.product.sku)}">
					<span class="painted-thumb">{#if d.product.image}<img src={d.product.image} alt="" loading="lazy" referrerpolicy="no-referrer" />{/if}</span>
					<span class="painted-title"><b>{d.product.title}</b><small>{shopLabel(d.product.shop)} · реально {verdictOf(d).real ? `−${Math.round(verdictOf(d).real ?? 0)}%` : '0%'}</small></span>
					<span class="painted-claim"><s>−{Math.round(d.drop_pct ?? 0)}%</s><small>+{Math.round(gap)} п.п.</small></span>
				</a>
			{/each}
		</div>
	</section>
{/if}

<style>
	.group-picks { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
	.group-pick {
		display: grid; gap: 6px; padding: 14px; border-radius: var(--radius); text-decoration: none;
		background: var(--surface); border: 1px solid var(--line);
	}
	.group-pick:hover { border-color: var(--ink-4); }
	.gp-group { font-size: 12px; font-weight: 700; color: var(--ink-3); }
	.gp-thumb { height: 110px; border-radius: 12px; background: var(--photo); display: grid; place-items: center; overflow: hidden; }
	.gp-thumb img { max-height: 92px; max-width: 80%; object-fit: contain; }
	.gp-title { font-size: 13px; font-weight: 600; color: var(--ink); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 36px; }
	.gp-price { display: flex; align-items: baseline; gap: 8px; }
	.gp-price b { font-family: var(--font-mono); font-size: 17px; color: var(--ink); }
	.gp-price em { font-style: normal; font-weight: 700; font-size: 12px; color: var(--success); background: var(--success-bg); padding: 1px 7px; border-radius: 999px; }
	.gp-shop { font-size: 12px; color: var(--ink-4); }
</style>
