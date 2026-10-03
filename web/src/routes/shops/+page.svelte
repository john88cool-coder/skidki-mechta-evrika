<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import { formatPrice } from '$lib/utils/format';
	import { verdictOf, realRank } from '$lib/utils/verdict';
	import { RefreshCw } from '@lucide/svelte';

	let perShop = $derived(
		dashboard.shops
			.map((shop) => {
				const deals = dashboard.deals.filter((d) => d.product.shop === shop.name);
				const claimed = deals.filter((d) => d.drop_pct);
				const checked = claimed.filter((d) => verdictOf(d).kind !== 'unknown');
				const painted = checked.filter((d) => verdictOf(d).kind === 'painted').length;
				const real = deals.filter((d) => { const k = verdictOf(d).kind; return k === 'honest' || k === 'inflated'; })
					.sort((a, b) => realRank(b) - realRank(a));
				return { shop, claimed: claimed.length, checked: checked.length, painted, real, share: checked.length ? painted / checked.length : null };
			})
			// Честные — выше: сортировка по доле нарисованных.
			.sort((a, b) => (a.share ?? 2) - (b.share ?? 2))
	);
</script>

<svelte:head><title>Магазины — skidki</title></svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Источники</p>
		<h1 class="page-heading">Честность <em>магазинов</em></h1>
		<p class="page-description">
			Какая доля скидок на ценниках подтверждается историей цены и сколько товаров в магазине реально подешевело. Честные — выше.
		</p>
	</div>
	<button onclick={() => dashboard.refresh()} class="reset-btn">
		<RefreshCw size={14} class={dashboard.loading ? 'animate-spin' : ''} /> Обновить
	</button>
</div>

<div class="grid gap-4">
	{#each perShop as row, i (row.shop.name)}
		<div class="shop-block">
			<div class="shop-rank">{i + 1}</div>
			<div class="min-w-0 flex-1">
				<ShopStatusCard shop={row.shop} />
				<div class="shop-stats">
					<div class="stat">
						<p>Нарисовано</p>
						<p class="big" class:bad={(row.share ?? 0) >= 0.5}>{row.share === null ? '—' : Math.round(row.share * 100) + '%'}</p>
						<p class="sub">{row.checked ? `${row.painted} из ${row.checked} проверенных` : 'нечего проверить'}</p>
					</div>
					<div class="stat">
						<p>Реально подешевело</p>
						<p class="big good">{row.real.length}</p>
						<p class="sub"><a href="{base}/deals?v=real&shop={row.shop.name}">смотреть →</a></p>
					</div>
					<div class="stat">
						<p>Лучшее снижение</p>
						{#if row.real[0]}
							<a class="best" href="{base}/item?shop={encodeURIComponent(row.real[0].product.shop)}&sku={encodeURIComponent(row.real[0].product.sku)}" title={row.real[0].product.title}>
								<b>−{Math.round(verdictOf(row.real[0]).real ?? 0)}%</b> · {formatPrice(row.real[0].product.price)}
							</a>
							<p class="sub truncate">{row.real[0].product.title}</p>
						{:else}<p class="big" style="color:var(--ink-4)">—</p>{/if}
					</div>
				</div>
			</div>
		</div>
	{/each}
</div>

<style>
	.shop-block { display: flex; gap: 16px; padding: 18px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--line); }
	.shop-rank {
		width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0; display: grid; place-items: center;
		font-family: var(--font-mono); font-weight: 700; background: var(--paper-2); color: var(--ink-3); border: 1px solid var(--line);
	}
	.shop-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
	.stat { border-radius: 12px; padding: 10px 12px; background: var(--paper-2); border: 1px solid var(--line); min-width: 0; }
	.stat p:first-child { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-4); }
	.stat .big { font-family: var(--font-mono); font-size: 20px; font-weight: 700; color: var(--ink); margin-top: 2px; }
	.stat .big.bad { color: var(--bad); }
	.stat .big.good { color: var(--success); }
	.stat .sub { font-size: 12px; color: var(--ink-4); margin-top: 2px; }
	.stat .sub a { color: var(--ink-3); text-decoration: none; }
	.stat .sub a:hover { color: var(--ink); }
	.best { display: inline-block; margin-top: 4px; font-family: var(--font-mono); font-size: 14px; color: var(--ink); text-decoration: none; }
	.best b { color: var(--success); }
	.best:hover { text-decoration: underline; text-underline-offset: 3px; }
	@media (max-width: 640px) {
		.shop-block { padding: 14px; gap: 10px; }
		.shop-rank { display: none; }
		.shop-stats { grid-template-columns: minmax(0, 1fr); }
	}
</style>
