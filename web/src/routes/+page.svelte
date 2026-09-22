<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard, fetchHistory } from '$lib/stores/data.svelte';
	import DealCard from '$lib/components/DealCard.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { formatPrice, shopLabel, groupLabel, formatPctValue, timeAgo } from '$lib/utils/format';
	import type { ProductHistory } from '$lib/types';
	import { ArrowRight, Sparkles, TrendingDown, ShieldCheck, Timer, Heart, Wallet, Trophy, Copy, Check } from '@lucide/svelte';
	import { favorites } from '$lib/stores/favorites.svelte';

	let featured = $state<ProductHistory | null>(null);
	const topCount = 8;

	$effect(() => {
		const best = dashboard.deals[0];
		if (!best) return;
		const version = dashboard.data?.updated_at;
		let cancelled = false;
		fetchHistory(best.product.shop, best.product.sku).then((data) => {
			if (!cancelled) featured = data;
		});
		return () => { cancelled = true; };
	});

	let byGroup = $derived.by(() => {
		const acc = new Map<string, { count: number; total: number }>();
		for (const d of dashboard.deals) {
			const key = d.product.group ?? 'other';
			const row = acc.get(key) ?? { count: 0, total: 0 };
			row.count += 1;
			row.total += d.drop_pct ?? 0;
			acc.set(key, row);
		}
		return [...acc.entries()]
			.map(([key, row]) => ({ key, count: row.count, avg: row.total / row.count }))
			.sort((a, b) => b.count - a.count);
	});

	// Полосы групп — в масштабе к самой глубокой группе: при множителе 1.6
	// все группы от −62% упирались в 100% и полосы были одинаковыми.
	// Полоса — доля предложений группы (объём), процент — средняя глубина.
	// Средние у групп близки (−58…−64%), полосы по ним выходили одинаковыми.
	let maxGroupCount = $derived(Math.max(1, ...byGroup.map((row) => row.count)));
	// Свежесть среза: «live» висел и на суточных данных.
	let updatedAt = $derived(dashboard.data?.updated_at ?? null);
	let stale = $derived(updatedAt ? Date.now() - new Date(updatedAt).getTime() > 6 * 3600_000 : true);

	let bestDeal = $derived(dashboard.deals[0] ?? null);
	let totalSavings = $derived(
		dashboard.deals.reduce((s, d) => s + Math.max(0, (d.product.old_price ?? d.product.price) - d.product.price), 0)
	);
	let deepestByShop = $derived.by(() => {
		const m = new Map<string, number>();
		for (const d of dashboard.deals) {
			const k = d.product.shop;
			const v = d.drop_pct ?? 0;
			if (!m.has(k) || v > (m.get(k) ?? 0)) m.set(k, v);
		}
		return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
	});
	let copiedHome = $state(false);
	function copyHome() {
		const lines = dashboard.deals.slice(0, 8).map((d) => d.product.title + ' \u2014 ' + d.product.price.toLocaleString('ru-RU') + ' \u20B8 \u00B7 ' + d.product.url);
		const text = lines.join('\n');
		navigator.clipboard.writeText(text).catch(() => {});
		copiedHome = true;
		setTimeout(() => (copiedHome = false), 1600);
	}
</script>

<svelte:head>
	<title>skidki — мониторинг скидок в Казахстане</title>
	<meta name="description" content="Следим за ценами в 6 магазинах Казахстана. История цены, топ скидок, статус обходов." />
</svelte:head>

<!-- Hero -->
<section class="hero">
	<div class="hero-copy">
		<p class="hero-kicker">Казахстан · 6 магазинов · история каждой цены</p>
		<h1 class="hero-title">Хорошая цена — <i>проверенная</i> историей.</h1>
		<p class="hero-text">
			Сравниваем скидку магазина с реальными наблюдениями. Видишь, падала ли цена на самом деле — и решаешь спокойно.
		</p>
		<div class="hero-stats">
			<div class="hero-stat">
				<strong>{dashboard.stats.total_products ? dashboard.stats.total_products.toLocaleString('ru-RU') : '—'}</strong>
				<span>позиций</span>
			</div>
			<div class="hero-stat">
				<strong style="color:var(--hero-accent)">{dashboard.stats.total_deals || '—'}</strong>
				<span>предложений</span>
			</div>
			<div class="hero-stat">
				<strong>{dashboard.stats.avg_discount ? '\u2212' + formatPctValue(dashboard.stats.avg_discount) + '%' : '—'}</strong>
				<span>средняя скидка</span>
			</div>
		</div>
	</div>
	<div class="hero-card">
		<div class="hero-card-head">
			<h3>Динамика лидера</h3>
			{#if updatedAt}<span class="live-dot" class:stale title="Время последнего среза данных">{timeAgo(updatedAt)}</span>{/if}
		</div>
		{#if featured}
			<p class="truncate text-xs mb-3" style="color:var(--ink-3)" title={featured.product.title}>
				{shopLabel(featured.product.shop)} · {featured.product.title}
			</p>
			<PriceChart data={featured.history} height={176} labelFormatter={(d) => (d.length >= 10 ? d.slice(5) : d)} />
			<div class="mt-3 grid grid-cols-3 gap-2 text-center">
				<div class="rounded-xl p-2" style="background:var(--paper); border:1px solid var(--line)">
					<p class="text-[10px] tracking-widest uppercase" style="color:var(--ink-4)">минимум</p>
					<p class="font-mono text-sm font-bold" style="color:var(--success)">{formatPrice(featured.stats.min_90d)}</p>
				</div>
				<div class="rounded-xl p-2" style="background:var(--paper); border:1px solid var(--line)">
					<p class="text-[10px] tracking-widest uppercase" style="color:var(--ink-4)">медиана</p>
					<p class="font-mono text-sm font-bold" style="color:var(--ink)">{formatPrice(featured.stats.median_30d)}</p>
				</div>
				<div class="rounded-xl p-2" style="background:var(--accent-2); border:1px solid color-mix(in srgb, var(--accent) 18%, transparent)">
					<p class="text-[10px] tracking-widest uppercase" style="color:var(--accent)">сейчас</p>
					<p class="font-mono text-sm font-bold" style="color:var(--ink)">{formatPrice(featured.product.price)}</p>
				</div>
			</div>
		{:else}
			<div class="flex flex-1 items-center justify-center rounded-xl border border-dashed py-10 text-sm" style="border-color:var(--line); color:var(--ink-4)">
				История появится после нескольких обходов
			</div>
		{/if}
		{#if bestDeal}
			<a href="{base}/item?shop={encodeURIComponent(bestDeal.product.shop)}&sku={encodeURIComponent(bestDeal.product.sku)}" class="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold" style="color:var(--ink)">
				Открыть карточку <ArrowRight size={14} />
			</a>
		{/if}
	</div>
</section>

{#if dashboard.loading && !dashboard.data}
	<div class="product-grid">
		{#each Array(8) as _, i (i)}<SkeletonCard />{/each}
	</div>
{:else}
	<!-- Инсайты -->
	<section class="grid gap-3 sm:grid-cols-3 mb-6">
		<div class="rounded-2xl p-4 flex items-center gap-3" style="background:var(--surface); border:1px solid var(--line)">
			<span class="w-9 h-9 rounded-xl grid place-items-center shrink-0" style="background:var(--accent-2); color:var(--accent)"><Wallet size={16} /></span>
			<div class="min-w-0"><p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">Экономия на витрине</p><p class="font-mono font-bold" style="color:var(--ink)">{totalSavings.toLocaleString('ru-RU')} ₸</p></div>
		</div>
		<div class="rounded-2xl p-4 flex items-center gap-3" style="background:var(--surface); border:1px solid var(--line)">
			<span class="w-9 h-9 rounded-xl grid place-items-center shrink-0" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink-2)"><Trophy size={16} /></span>
			<div class="min-w-0"><p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">Лидеры по скидке</p><p class="text-xs font-medium truncate" style="color:var(--ink)">{deepestByShop.map(([k, v]) => shopLabel(k) + ' \u2212' + Math.round(v) + '%').join(' \u00B7 ') || '—'}</p></div>
		</div>
		<div class="rounded-2xl p-4 flex items-center justify-between gap-3" style="background:var(--surface); border:1px solid var(--line)">
			<div class="flex items-center gap-3 min-w-0"><span class="w-9 h-9 rounded-xl grid place-items-center shrink-0" style="background:var(--paper-2); border:1px solid var(--line); color:var(--ink-2)"><Heart size={16} /></span><div><p class="text-[11px] font-bold tracking-widest uppercase" style="color:var(--ink-4)">Избранное</p><p class="font-mono font-bold" style="color:var(--ink)">{favorites.count}</p></div></div>
			<button onclick={copyHome} class="shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-semibold" style="background:var(--ink); color:var(--on-ink)">{#if copiedHome}<Check size={12} /> Скопировано{:else}<Copy size={12} /> Копировать топ-8{/if}</button>
		</div>
	</section>

	<!-- KPI -->
	<section class="kpi-grid">
		<div class="kpi">
			<span class="kpi-label"><ShieldCheck size={14} /> Позиций в базе</span>
			<span class="kpi-value">{dashboard.stats.total_products.toLocaleString('ru-RU')}</span>
			<span class="kpi-hint">6 магазинов · обход по расписанию, обычно раз в 2–6 ч</span>
		</div>
		<div class="kpi">
			<span class="kpi-label"><Sparkles size={14} /> Предложений сегодня</span>
			<span class="kpi-value accent">{dashboard.stats.total_deals}</span>
			<span class="kpi-hint">Отобраны по реальной глубине скидки</span>
		</div>
		<div class="kpi">
			<span class="kpi-label"><TrendingDown size={14} /> Средняя скидка</span>
			<span class="kpi-value">−{formatPctValue(dashboard.stats.avg_discount)}%</span>
			<span class="kpi-hint">Медиана по витрине</span>
		</div>
	</section>

	<!-- Топ скидки -->
	<section style="margin-bottom:28px">
		<div class="section-head">
			<h2>Предложения <i>дня</i></h2>
			<a href="{base}/deals" class="section-link">Все {dashboard.deals.length} <ArrowRight size={14} /></a>
		</div>
		<div class="product-grid">
			{#each dashboard.deals.slice(0, topCount) as deal, i (deal.product.shop + deal.product.sku)}
				<DealCard {deal} rank={i + 1} />
			{:else}
				<div class="col-span-full rounded-2xl border border-dashed p-10 text-center" style="border-color:var(--line); color:var(--ink-3); background:var(--surface)">
					Пока нет скидок. Первый обход скоро появится.
				</div>
			{/each}
		</div>
	</section>

	<!-- Группы + магазины -->
	<div class="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
		<section class="rounded-2xl p-5" style="background:var(--surface); border:1px solid var(--line)">
			<h3 class="text-sm font-bold tracking-tight flex items-center gap-2" style="color:var(--ink)"><Timer size={14} /> Скидки по группам</h3>
			<p class="text-xs mt-1" style="color:var(--ink-4)">Полоса — число предложений, процент — средняя скидка</p>
			{#if byGroup.length}
				<div class="mt-4 space-y-3">
					{#each byGroup as row (row.key)}
						<div class="flex items-center gap-3">
							<span class="flex-1 truncate text-sm font-medium" style="color:var(--ink-2)">{groupLabel(row.key)}</span>
							<div class="group-bar"><i style="width:{(row.count / maxGroupCount) * 100}%"></i></div>
							<span class="font-mono text-sm font-bold" style="color:var(--accent)">−{row.avg.toFixed(0)}%</span>
							<span class="text-xs w-7 text-right" style="color:var(--ink-4)">{row.count}</span>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm mt-4" style="color:var(--ink-4)">Нет данных</p>
			{/if}
		</section>

		<section class="rounded-2xl p-5" style="background:var(--surface); border:1px solid var(--line)">
			<div class="flex items-center justify-between">
				<h3 class="text-sm font-bold tracking-tight" style="color:var(--ink)">Магазины</h3>
				<a href="{base}/shops" class="text-xs font-semibold inline-flex items-center gap-1" style="color:var(--ink-3)">Подробнее <ArrowRight size={12} /></a>
			</div>
			<div class="mt-4 space-y-2">
				{#each dashboard.shops as shop (shop.name)}
					<ShopStatusCard {shop} />
				{:else}
					<div class="rounded-xl p-6 text-center text-sm" style="color:var(--ink-4)">Данных обходов пока нет.</div>
				{/each}
			</div>
		</section>
	</div>
{/if}
