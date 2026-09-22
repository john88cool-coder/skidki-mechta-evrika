<script lang="ts">
	import { page } from '$app/state';
	import { dashboard, fetchHistory } from '$lib/stores/data.svelte';
	import { recentPrices, formatChange } from '$lib/utils/history';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice, formatDate, shopLabel, badgeTone } from '$lib/utils/format';
	import type { ProductHistory } from '$lib/types';
	import { ArrowLeft, ExternalLink, ArrowDown, TrendingDown, Heart, Share2, Copy, Check } from '@lucide/svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import { base } from '$app/paths';

	let shop = $derived(page.url.searchParams.get('shop') ?? '');
	let sku = $derived(page.url.searchParams.get('sku') ?? '');
	let backHref = $derived.by(() => {
		const from = page.url.searchParams.get('from');
		if (!from?.startsWith(`${base}/`)) return `${base}/deals`;
		try {
			const target = new URL(from, page.url.origin);
			return target.origin === page.url.origin && [base + '/', base + '/deals'].includes(target.pathname) ? target.pathname + target.search : `${base}/deals`;
		} catch { return `${base}/deals`; }
	});

	let history = $state<ProductHistory | null>(null);
	let loading = $state(true);

	$effect(() => {
		const version = dashboard.data?.updated_at;
		if (!shop || !sku) { loading = false; return; }
		loading = true;
		let cancelled = false;
		fetchHistory(shop, sku).then((data) => { if (!cancelled) { history = data; loading = false; } });
		return () => { cancelled = true; };
	});

	let fav = $derived(history ? favorites.has(favId(history.product.shop, history.product.sku)) : false);
	let copiedItem = $state(false);
	let copiedLink = $state(false);
	function toggleFav() { if (!history) return; favorites.toggle(favId(history.product.shop, history.product.sku)); }
	function copyLink() { navigator.clipboard.writeText(location.href).catch(()=>{}); copiedLink=true; setTimeout(()=>copiedLink=false,1400); }
	async function shareItem() {
		if (!history) return;
		const url = location.href;
		try { if (navigator.share) { await navigator.share({ title: history.product.title, url }); return; } } catch {}
		navigator.clipboard.writeText(url).catch(()=>{}); copiedItem=true; setTimeout(()=>copiedItem=false,1400);
	}
	let dealForItem = $derived(dashboard.deals.find(d => d.product.shop === (history?.product.shop ?? shop) && d.product.sku === (history?.product.sku ?? sku)));
	let change = $derived.by(() => {
		if (!history || history.history.length < 2) return null;
		const first = history.history[0].price;
		const last = history.history[history.history.length - 1].price;
		if (first === last) return null;
		return { delta: last - first, pct: ((last - first) / first) * 100 };
	});
</script>

<svelte:head><title>{history?.product.title ?? 'История цены'} — skidki</title></svelte:head>

<a href={backHref} class="inline-flex items-center gap-1.5 text-sm font-medium mb-5" style="color:var(--ink-3)">
	<ArrowLeft size={14} /> К скидкам
</a>

{#if loading}
	<div class="flex h-64 items-center justify-center"><span class="h-8 w-8 animate-spin rounded-full border-[3px] border-[var(--line)] border-t-[var(--accent)]"></span></div>
{:else if !history}
	<div class="rounded-2xl p-12 text-center" style="background:white; border:1px solid var(--line); color:var(--ink-3)">История этого товара ещё не собрана — нужен хотя бы один обход.</div>
{:else}
	<div class="flex gap-4 mb-6">
		{#if history.product.image}
			<img src={history.product.image} alt={history.product.title} loading="lazy" referrerpolicy="no-referrer" class="h-28 w-28 shrink-0 rounded-2xl object-contain p-3" style="background:white; border:1px solid var(--line)" />
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<span class="meta-pill">{shopLabel(history.product.shop)}</span>
				{#if history.product.brand}<span class="text-xs" style="color:var(--ink-4)">{history.product.brand}</span>{/if}
				{#if history.product.category}<span class="text-xs" style="color:var(--ink-4)">· {history.product.category}</span>{/if}
			</div>
			<h1 class="mt-2 text-xl font-bold tracking-tight leading-tight" style="color:var(--ink)">{history.product.title}</h1>
			{#if dealForItem?.badges?.length || dealForItem?.is_pick}
			<div class="badge-row" style="margin-top:10px">
				{#each (dealForItem.badges ?? []) as b (b)}<span class="badge badge-{badgeTone(b)}">{b}</span>{/each}
				{#if dealForItem?.fair_discount != null}<span class="badge badge-fair">честно {dealForItem.fair_discount}%</span>{/if}
				{#if dealForItem?.value_score != null}<span class="badge badge-score">value {dealForItem.value_score}</span>{/if}
				{#if dealForItem?.inflated_gap != null && dealForItem.inflated_gap >= 15}<span class="badge badge-warn" title="Завышение зачёркнутой">{dealForItem.inflated_gap} п.п. завышено</span>{/if}
			</div>
			{/if}
			<div class="mt-3 flex flex-wrap items-baseline gap-3">
				<span class="font-mono text-3xl font-black tracking-tight" style="color:var(--ink)">{formatPrice(history.product.price)}</span>
				{#if change}
					<span class="inline-flex items-center gap-1 text-sm font-semibold px-2.5 py-1 rounded-full" style="background: {change.delta < 0 ? 'var(--success-bg)' : 'var(--accent-2)'}; color:{change.delta < 0 ? 'var(--success)' : 'var(--accent)'}">
						{#if change.delta < 0}<ArrowDown size={14} />{/if}
						{formatPrice(Math.abs(change.delta))} ({change.pct.toFixed(1)}%)
					</span>
				{/if}
				<a href={history.product.url} target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-sm font-semibold" style="color:var(--ink-3)"><ExternalLink size={14} /> В магазине</a>
			</div>
			<div class="mt-4 flex flex-wrap gap-2">
				<button onclick={toggleFav} class="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-semibold" style="background:{fav ? 'var(--accent)' : 'white'}; color:{fav ? 'white' : 'var(--ink-2)'}; border:1px solid {fav ? 'var(--accent)' : 'var(--line)'}"><Heart size={14} fill={fav ? 'currentColor' : 'none'} /> {fav ? 'В избранном' : 'В избранное'}</button>
				<button onclick={shareItem} class="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-semibold" style="background:white; border:1px solid var(--line); color:var(--ink-2)">{#if copiedItem}<Check size={14} /> Скопировано{:else}<Share2 size={14} /> Поделиться{/if}</button>
				<button onclick={copyLink} class="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-sm font-medium" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink-3)">{#if copiedLink}<Check size={14} />{:else}<Copy size={14} />{/if} Ссылка</button>
			</div>
		</div>
	</div>

	<section class="rounded-2xl p-5 mb-5" style="background:white; border:1px solid var(--line)">
		<h2 class="text-sm font-bold tracking-tight flex items-center gap-2" style="color:var(--ink)"><TrendingDown size={14} /> История цены</h2>
		<div class="mt-4"><PriceChart data={history.history} height={260} labelFormatter={(d) => (d.length >= 10 ? formatDate(d) : d)} /></div>
	</section>

	<section class="rounded-2xl p-5 mb-5" style="background:white; border:1px solid var(--line)">
		<h2 class="font-bold tracking-tight" style="color:var(--ink)">Последние наблюдения</h2>
		<p class="text-xs mt-1" style="color:var(--ink-4)">Изменение к предыдущей записи · новые сверху</p>
		<div class="overflow-x-auto mt-3">
			<table class="w-full text-left text-sm">
				<thead><tr class="text-xs" style="color:var(--ink-4); border-bottom:1px solid var(--line)"><th class="py-2 font-semibold">Дата</th><th class="font-semibold">Цена</th><th class="font-semibold">Изменение</th></tr></thead>
				<tbody>
					{#each recentPrices(history.recent ?? history.history).reverse() as point}
						<tr style="border-bottom:1px solid var(--paper-2)"><td class="py-3" style="color:var(--ink-3)"><time datetime={point.date}>{formatDate(point.date)}</time></td><td class="font-mono font-medium" style="color:var(--ink)">{formatPrice(point.price)}</td><td class:price-down={point.change !== null && point.change < 0} class:price-up={point.change !== null && point.change > 0} class="font-mono text-sm">{formatChange(point.change)}</td></tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	{#if dealForItem}
	{@const related = dashboard.deals.filter(d => d.product.shop !== dealForItem!.product.shop || d.product.sku !== dealForItem!.product.sku).filter(d => (d.product.group && d.product.group === dealForItem!.product.group) || (d.product.brand && d.product.brand === dealForItem!.product.brand)).slice(0,4)}
	{#if related.length}
	<section class="rounded-2xl p-5 mb-5" style="background:white; border:1px solid var(--line)">
		<h2 class="font-bold tracking-tight" style="color:var(--ink)">Похожие</h2>
		<p class="text-xs mt-1" style="color:var(--ink-4)">Та же группа/бренд — альтернативы для сравнения.</p>
		<div class="grid gap-2 mt-3">
			{#each related as r (r.product.shop + r.product.sku)}<a href="{r.product.url}" target="_blank" rel="noopener" class="flex items-center justify-between gap-3 p-3 rounded-xl hover:shadow-[var(--shadow)] transition-shadow" style="border:1px solid var(--line)"><span class="text-sm font-medium truncate" style="color:var(--ink)">{r.product.title}</span><span class="font-mono text-sm font-bold shrink-0" style="color:var(--ink)">{formatPrice(r.product.price)}</span></a>{/each}
		</div>
	</section>
	{/if}
	{/if}
	<section class="stat-grid">
		<div class="stat-card"><p>Минимум за период</p><p style="color:var(--success)">{formatPrice(history.stats.min_90d)}</p></div>
		<div class="stat-card"><p>Медиана</p><p style="color:var(--ink)">{formatPrice(history.stats.median_30d)}</p></div>
		<div class="stat-card"><p>Точек наблюдения</p><p style="color:var(--ink)">{history.history.length}</p></div>
	</section>
{/if}

<style>
.badge-row { display:flex; flex-wrap:wrap; gap:6px; }
.badge { font-size:10px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; padding:3px 7px; border-radius:999px; border:1px solid var(--line); }
.badge-pick { background: var(--ink); color:white; border-color: var(--ink); }
.badge-fair { background: var(--success-bg); color: var(--success); border-color: color-mix(in srgb, var(--success) 18%, transparent); }
.badge-brand { background: #fff7e6; color:#9a6a0a; border-color:#ffe2a8; }
.badge-warn { background: var(--accent-2); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 18%, transparent); }
.badge-score { background: var(--paper-2); color: var(--ink-2); }
</style>
