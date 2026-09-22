<script lang="ts">
	import { dashboard } from '$lib/stores/data.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import { groupLabel, formatPrice, formatPctValue } from '$lib/utils/format';
	import { RefreshCw, Store } from '@lucide/svelte';

	let perShop = $derived(
		dashboard.shops.map((shop) => {
			const deals = dashboard.deals.filter((d) => d.product.shop === shop.name);
			const avg = deals.length ? deals.reduce((s, d) => s + (d.drop_pct ?? 0), 0) / deals.length : 0;
			const best = deals.reduce<(typeof deals)[number] | null>((acc, d) => (!acc || (d.drop_pct ?? 0) > (acc.drop_pct ?? 0) ? d : acc), null);
			return { shop, deals: deals.length, avg, best };
		})
	);
</script>

<svelte:head><title>Магазины — skidki</title></svelte:head>

<div class="flex items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Источники</p>
		<h1 class="page-heading" style="font-size:clamp(26px,3vw,34px)">Магазины</h1>
		<p class="page-description">Статус обходов, наполненность и лучшие находки по каждому источнику.</p>
	</div>
	<button onclick={() => dashboard.refresh()} class="inline-flex items-center gap-2 h-10 px-4 rounded-full text-sm font-semibold shrink-0" style="background:var(--surface); border:1px solid var(--line); color:var(--ink-2)">
		<RefreshCw size={14} class={dashboard.loading ? 'animate-spin' : ''} /> Обновить
	</button>
</div>

<div class="grid gap-4">
	{#each perShop as row (row.shop.name)}
		<div class="rounded-2xl p-5" style="background:var(--surface); border:1px solid var(--line)">
			<ShopStatusCard shop={row.shop} />
			<div class="mt-4 grid grid-cols-3 gap-3">
				<div class="rounded-xl px-3 py-3" style="background:var(--paper-2); border:1px solid var(--line)">
					<p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">В топе</p>
					<p class="font-mono text-lg font-bold mt-1" style="color:var(--ink)">{row.deals}</p>
				</div>
				<div class="rounded-xl px-3 py-3" style="background:var(--paper-2); border:1px solid var(--line)">
					<p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">Средняя</p>
					<p class="font-mono text-lg font-bold mt-1" style="color:var(--ink)">{row.deals ? `−${formatPctValue(row.avg)}%` : "—"}</p>
				</div>
				<div class="rounded-xl px-3 py-3" style="background:var(--paper-2); border:1px solid var(--line)">
					<p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">Лучшая</p>
					{#if row.best}
						<a href={row.best.product.url} target="_blank" rel="noopener" class="font-mono text-sm font-bold hover:underline underline-offset-4" style="color:var(--accent)" title={row.best.product.title}>
							−{Math.round(row.best.drop_pct ?? 0)}% · {formatPrice(row.best.product.price)}
						</a>
					{:else}<p class="font-mono text-sm font-bold mt-1" style="color:var(--ink-4)">—</p>{/if}
				</div>
			</div>
		</div>
	{/each}
</div>

<section class="mt-8">
	<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight" style="color:var(--ink)"><Store size={16} /> Скидки по группам</h2>
	<div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
		{#each Object.entries(dashboard.deals.reduce<Record<string, number>>((acc, d) => { const k = d.product.group ?? 'other'; acc[k] = (acc[k] ?? 0) + 1; return acc; }, {})) as [key, count] (key)}
			<div class="flex items-center justify-between rounded-xl px-4 py-3" style="background:var(--surface); border:1px solid var(--line)">
				<span class="text-sm font-medium" style="color:var(--ink-2)">{groupLabel(key)}</span>
				<span class="font-mono font-bold px-2.5 py-1 rounded-full text-sm" style="background:var(--paper-2); color:var(--ink)">{count}</span>
			</div>
		{:else}
			<p class="text-sm" style="color:var(--ink-4)">Нет данных</p>
		{/each}
	</div>
</section>
