<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard, fetchHistory } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import TruthMeter from '$lib/components/TruthMeter.svelte';
	import { formatPrice, shopLabel, groupLabel, timeAgo } from '$lib/utils/format';
	import { verdictOf, realRank, countVerdicts, isReal } from '$lib/utils/verdict';
	import type { ProductHistory } from '$lib/types';
	import { ArrowRight, Ban, TrendingDown, Search } from '@lucide/svelte';
	import { favorites } from '$lib/stores/favorites.svelte';
	import { goto } from '$app/navigation';

	let checkQuery = $state('');

	/** Подписанная форма «Проверить товар или ссылку» → /search?q=… через URLSearchParams. */
	function submitCheck(e: SubmitEvent) {
		e.preventDefault();
		const value = checkQuery.trim();
		if (!value) return;
		goto(`${base}/search?${new URLSearchParams({ q: value })}`);
	}

	let featured = $state<ProductHistory | null>(null);

	/** Реальные снижения — главное, ради чего существует ИС. */
	let realDeals = $derived(
		dashboard.deals
			.filter((d) => isReal(verdictOf(d).kind))
			.sort((a, b) => realRank(b) - realRank(a))
	);
	/** Скидки на ценнике, которые история не подтверждает, — от самых «громких». */
	let painted = $derived(
		dashboard.deals.filter((d) => verdictOf(d).kind === 'painted').sort((a, b) => (b.drop_pct ?? 0) - (a.drop_pct ?? 0))
	);
	/** Витрина «по ценнику»: только позиции с зачёркнутой ценой — их и проверяем. */
	let claimedDeals = $derived(dashboard.deals.filter((d) => d.drop_pct));
	let counts = $derived(countVerdicts(claimedDeals));
	let best = $derived(realDeals[0] ?? null);

	$effect(() => {
		const target = best;
		if (!target) { featured = null; return; }
		void dashboard.data?.updated_at;
		let cancelled = false;
		fetchHistory(target.product.shop, target.product.sku).then((data) => { if (!cancelled) featured = data; });
		return () => { cancelled = true; };
	});

	/** Честность магазина: доля нарисованных среди его скидок на ценнике (с историей). */
	let honesty = $derived.by(() => {
		const rows = new Map<string, { checked: number; painted: number; real: number }>();
		for (const d of dashboard.deals) {
			const k = verdictOf(d).kind;
			const row = rows.get(d.product.shop) ?? { checked: 0, painted: 0, real: 0 };
			if (d.drop_pct && k !== 'unknown') { row.checked += 1; if (k === 'painted') row.painted += 1; }
			if (isReal(k)) row.real += 1;
			rows.set(d.product.shop, row);
		}
		return [...rows.entries()]
			.map(([shop, r]) => ({ shop, ...r, share: r.checked ? r.painted / r.checked : null }))
			.sort((a, b) => (a.share ?? 2) - (b.share ?? 2));
	});
	let byGroup = $derived.by(() => {
		const acc = new Map<string, number>();
		for (const d of realDeals) acc.set(d.product.group ?? 'other', (acc.get(d.product.group ?? 'other') ?? 0) + 1);
		return [...acc.entries()].sort((a, b) => b[1] - a[1]);
	});
	let maxGroup = $derived(Math.max(1, ...byGroup.map(([, n]) => n)));

	let updatedAt = $derived(dashboard.freshness.oldest);
	let stale = $derived(dashboard.freshness.stale);
</script>

<svelte:head>
	<title>skidki — какие скидки в Казахстане настоящие</title>
	<meta name="description" content="Проверяем скидки шести магазинов Казахстана по истории цены: честные, завышенные и нарисованные." />
</svelte:head>

<section class="hero">
	<div class="hero-copy">
		<p class="hero-kicker">Казахстан · {dashboard.shops.length || 6} магазинов · история каждой цены</p>
		<h1 class="hero-title">Хорошая цена — <i>проверенная</i> историей.</h1>
		<p class="hero-text">
			Магазин пишет «−80%», а мы смотрим, сколько товар стоил последний месяц. Остаётся то, что правда подешевело.
		</p>
		{#if claimedDeals.length}
			<TruthMeter {counts} total={claimedDeals.length} />
		{/if}
		<form class="hero-check" onsubmit={submitCheck}>
			<label class="hero-check-label" for="hero-check-q">Проверить товар или ссылку</label>
			<div class="hero-check-row">
				<div class="hero-check-input">
					<Search size={16} />
					<input
						id="hero-check-q"
						type="search"
						bind:value={checkQuery}
						placeholder="Название, модель, SKU или ссылка…"
					/>
				</div>
				<button type="submit">Проверить</button>
			</div>
		</form>
		<div class="hero-stats">
			<div class="hero-stat">
				<strong>{dashboard.stats.total_products ? dashboard.stats.total_products.toLocaleString('ru-RU') : '—'}</strong>
				<span>позиций под наблюдением</span>
			</div>
			<a class="hero-stat link" href="{base}/deals?v=real">
				<strong style="color:var(--hero-good)">{realDeals.length}</strong>
				<span>реально подешевели →</span>
			</a>
		</div>
	</div>

	<div class="hero-card">
		<div class="hero-card-head">
			<h3>Лучшее реальное снижение</h3>
			{#if updatedAt}<span class="live-dot" class:stale title="Самый давний обход среди магазинов">{timeAgo(updatedAt)}</span>{/if}
		</div>
		{#if best && featured}
			<a class="featured-title" href="{base}/item?shop={encodeURIComponent(best.product.shop)}&sku={encodeURIComponent(best.product.sku)}">
				{shopLabel(best.product.shop)} · {best.product.title}
			</a>
			<PriceChart data={featured.history} height={170} labelFormatter={(d) => (d.length >= 10 ? d.slice(8, 10) + '.' + d.slice(5, 7) : d)} />
			<div class="featured-stats">
				<div><p>обычно</p><p class="mono">{formatPrice(best.base_price ?? featured.stats.median_30d)}</p></div>
				<div class="now"><p>сейчас</p><p class="mono">{formatPrice(best.product.price)}</p></div>
				<div class="gain"><p>реально</p><p class="mono">−{Math.round(verdictOf(best).real ?? 0)}%</p></div>
			</div>
		{:else if dashboard.loading}
			<div class="featured-empty">Загружаем историю…</div>
		{:else}
			<div class="featured-empty">Реальные снижения появятся, когда накопится история (3+ дня).</div>
		{/if}
	</div>
</section>

{#if dashboard.loading && !dashboard.data}
	<div class="product-grid">{#each Array(8) as _, i (i)}<SkeletonCard />{/each}</div>
{:else}
	<section class="block">
		<div class="section-head">
			<h2><TrendingDown size={20} class="inline -mt-1 mr-1" /> Реально <i>подешевело</i></h2>
			<a href="{base}/deals?v=real" class="section-link">Все {realDeals.length} <ArrowRight size={14} /></a>
		</div>
		{#if realDeals.length}
			<div class="product-grid">
				{#each realDeals.slice(0, 8) as deal (deal.product.shop + deal.product.sku)}<DealCard {deal} />{/each}
			</div>
		{:else}
			<div class="empty-state"><p style="color:var(--ink-3)">Подтверждённых снижений пока нет — нужна история хотя бы за 3 дня.</p></div>
		{/if}
	</section>

	{#if painted.length}
		<section class="block">
			<div class="section-head">
				<h2><Ban size={20} class="inline -mt-1 mr-1" /> Осторожно: <i>нарисованные</i></h2>
				<a href="{base}/deals?v=painted" class="section-link">Все {painted.length} <ArrowRight size={14} /></a>
			</div>
			<p class="block-lead">Громкий процент на ценнике, а цена за всё время наблюдений не двигалась. Такие «скидки» не стоит принимать за повод купить.</p>
			<div class="painted-list">
				{#each painted.slice(0, 6) as d (d.product.shop + d.product.sku)}
					<a class="painted-row" href="{base}/item?shop={encodeURIComponent(d.product.shop)}&sku={encodeURIComponent(d.product.sku)}">
						<span class="painted-thumb">{#if d.product.image}<img src={d.product.image} alt="" loading="lazy" referrerpolicy="no-referrer" />{/if}</span>
						<span class="painted-title"><b>{d.product.title}</b><small>{shopLabel(d.product.shop)} · цена держится {formatPrice(d.product.price)}</small></span>
						<span class="painted-claim"><s>−{Math.round(d.drop_pct ?? 0)}%</s><small>на ценнике</small></span>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<div class="bottom-grid">
		<section class="panel">
			<h3>Где подешевело</h3>
			<p class="panel-sub">Реальные снижения по группам</p>
			<div class="group-rows">
				{#each byGroup as [key, n] (key)}
					<a class="group-row" href="{base}/deals?v=real&group={key}">
						<span>{groupLabel(key)}</span>
						<div class="group-bar"><i style="width:{(n / maxGroup) * 100}%"></i></div>
						<b>{n}</b>
					</a>
				{:else}
					<p class="panel-sub">Пока нет данных</p>
				{/each}
			</div>
		</section>
		<section class="panel">
			<div class="flex items-center justify-between">
				<h3>Честность магазинов</h3>
				<a href="{base}/shops" class="panel-link">Подробнее <ArrowRight size={12} /></a>
			</div>
			<p class="panel-sub">Доля нарисованных среди скидок на ценниках, которые удалось проверить</p>
			<div class="group-rows">
				{#each honesty as h (h.shop)}
					<div class="group-row static">
						<span>{shopLabel(h.shop)}</span>
						<div class="honesty-bar" title="нарисовано {h.painted} из {h.checked}">
							{#if h.share !== null}<i class="bad" style="width:{h.share * 100}%"></i>{/if}
						</div>
						<b>{h.share === null ? '—' : Math.round(h.share * 100) + '%'}</b>
					</div>
				{/each}
			</div>
		</section>
	</div>
{/if}

<style>
	.hero-check {
		margin-top: 20px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.hero-check-label {
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
	}
	.hero-check-row {
		display: flex;
		gap: 8px;
	}
	.hero-check-input {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 12px;
		height: 44px;
		border-radius: 12px;
		border: 1px solid color-mix(in srgb, var(--on-ink) 22%, transparent);
		background: color-mix(in srgb, var(--on-ink) 8%, transparent);
	}
	.hero-check-input input {
		flex: 1;
		height: 100%;
		background: transparent;
		border: none;
		outline: none;
		font-size: 14px;
		color: var(--ink);
	}
	.hero-check-input input::placeholder {
		color: var(--ink-4);
	}
	.hero-check-row button {
		height: 44px;
		padding: 0 18px;
		border-radius: 12px;
		font-weight: 600;
		font-size: 14px;
		background: var(--ink);
		color: var(--on-ink);
	}
</style>
