<script lang="ts">
	import { page } from '$app/state';
	import { dashboard, loadCatalogItem } from '$lib/stores/data.svelte';
	import { itemBackHref, priceViewOf, baseDelta, recentPrices, formatChange, type ItemCard } from '$lib/utils/history';
	import PriceChart from '$lib/components/PriceChart.svelte';
	import { formatPrice, formatDate, shopLabel } from '$lib/utils/format';
	import { verdictOf } from '$lib/utils/verdict';
	import { relatedDeals } from '$lib/utils/related';
	import { partialOffers, offersVisibleFor, type OffersState } from '$lib/utils/catalog-offers';
	import VerdictChip from '$lib/components/VerdictChip.svelte';
	import { getSnapshot } from '$lib/utils/snapshots';
	import { ArrowLeft, ExternalLink, ArrowDown, TrendingDown, Heart, Share2, Copy, Check, ArrowRightLeft } from '@lucide/svelte';
	import { favorites, favId } from '$lib/stores/favorites.svelte';
	import { catalog } from '$lib/stores/catalog.svelte';
	import type { CatalogIndex } from '$lib/types';
	import { base } from '$app/paths';

	let shop = $derived(page.url.searchParams.get('shop') ?? '');
	let sku = $derived(page.url.searchParams.get('sku') ?? '');
	/** Возврат — только явные пути приложения (/ , /deals, /search под base); внешние ссылки ведут к каталогу. */
	let backHref = $derived(itemBackHref(page.url.searchParams.get('from'), base, page.url.origin));

	/** Карточка товара: catalog-v2, старый срез или снимок избранного. */
	let card = $state<ItemCard | null>(null);
	let failed = $state<{ kind: 'missing' } | { kind: 'unavailable'; reason: string | null } | null>(null);
	let loading = $state(true);
	let retryTick = $state(0);

	$effect(() => {
		const tick = retryTick; // повтор по кнопке перезапускает загрузку того же товара
		if (!shop || !sku) { loading = false; card = null; failed = null; return; }
		loading = true;
		// Быстрый переход A → B: старое содержимое убираем сразу, ответ применим
		// только для активной пары (запоздавший ответ получает stale и отбрасывается).
		card = null;
		failed = null;
		offersState = null; // блок офферов предыдущего товара не показываем
		offersError = null;
		offersForIdentity = null;
		let cancelled = false;
		loadCatalogItem(shop, sku, () => !cancelled).then((res) => {
			if (cancelled || res.status === 'stale') return;
			if (res.status === 'found') card = res.card;
			else if (res.status === 'missing') failed = { kind: 'missing' };
			else failed = { kind: 'unavailable', reason: res.reason };
			loading = false;
		}).catch((e) => {
			if (cancelled) return;
			failed = { kind: 'unavailable', reason: e instanceof Error ? e.message : String(e) };
			loading = false;
		});
		return () => { cancelled = true; };
	});

	let fav = $derived(card ? favorites.has(favId(card.product.shop, card.product.sku)) : false);
	let copiedItem = $state(false);
	let copiedLink = $state(false);
	function toggleFav() { if (!card) return; favorites.toggle(favId(card.product.shop, card.product.sku), card.product); }
	function copyLink() { navigator.clipboard.writeText(location.href).catch(()=>{}); copiedLink=true; setTimeout(()=>copiedLink=false,1400); }
	async function shareItem() {
		if (!card) return;
		const url = location.href;
		try { if (navigator.share) { await navigator.share({ title: card.product.title, url }); return; } } catch {}
		navigator.clipboard.writeText(url).catch(()=>{}); copiedItem=true; setTimeout(()=>copiedItem=false,1400);
	}
	let dealForItem = $derived(dashboard.deals.find(d => d.product.shop === (card?.product.shop ?? shop) && d.product.sku === (card?.product.sku ?? sku)) ?? null);
	/** Общий view model цены: одна база и один вывод для витрины и карточки каталога. */
	let view = $derived.by(() => {
		if (!card) return null;
		return priceViewOf({
			price: card.product.price,
			basePrice: card.basePrice,
			coverageDays: card.coverageDays,
			firstSeen: card.points[0]?.date ?? null,
			lastSeen: card.lastSeen,
			available: card.product.in_stock !== false,
			deal: dealForItem
		});
	});
	let verdict = $derived(view?.verdict ?? null);
	/** Совет покупателю — вывод из вердикта, а не ещё одна цифра. */
	let advice = $derived.by(() => {
		if (!verdict) return null;
		if (verdict.kind === 'honest') return { tone: 'good', title: 'Можно брать', text: verdict.hint };
		if (verdict.kind === 'inflated') return { tone: 'warn', title: 'Скидка есть, но меньше заявленной', text: verdict.hint };
		if (verdict.kind === 'pumped') return { tone: 'warn', title: 'Накрутка перед скидкой', text: verdict.hint };
		if (verdict.kind === 'painted') return { tone: 'bad', title: 'Не спешите', text: verdict.hint + ' Реальной выгоды сейчас нет.' };
		return { tone: 'muted', title: 'Пока рано судить', text: verdict.hint };
	});
	/** Выгода считается от той же «обычной цены», что и вердикт: одна база на всю страницу. */
	let saving = $derived.by(() => {
		if (!card) return null;
		if (verdict?.real) return baseDelta(card.product.price, dealForItem?.base_price);
		// Позиция без акции, но дешевле своей обычной цены — отклонение в тенге.
		if (view?.kind === 'below' && view.deviation != null && view.percent != null) {
			return { delta: view.deviation, pct: view.percent };
		}
		return null;
	});
	/** «обычно X» — база выше текущей цены; база позиции со скидкой приоритетна. */
	let baseLine = $derived.by(() => {
		if (!card) return null;
		const price = card.product.price;
		if (dealForItem?.base_price && dealForItem.base_price > price * 1.01) return dealForItem.base_price;
		if (dealForItem) return null;
		if (view && view.kind !== 'delisted' && view.basePrice != null && view.basePrice > price * 1.01) return view.basePrice;
		return null;
	});

	/* ===== Предложения той же комплектации в других магазинах (задача 6) ===== */

	type OffersResult =
		| { kind: 'hidden' } // без подтверждённого артикула блок скрыт
		| { kind: 'ready'; state: OffersState }
		| { kind: 'empty'; partial: boolean }; // совпадений нет
	let offersState = $state<OffersResult | null>(null); // null — блок ещё не запрашивали
	let offersLoading = $state(false);
	/** Сбой загрузки офферов: виден сам по себе, даже если состояние ещё не установлено. */
	let offersError = $state<string | null>(null);
	/** Товар, для которого собраны офферы: ответ запоздавшего запроса не применяется. */
	let offersForIdentity = $state<string | null>(null);

	async function comparePrices() {
		if (!card || card.source !== 'catalog-v2' || offersLoading) return;
		const requested = `${card.product.shop}:${card.product.sku}`;
		offersLoading = true;
		offersError = null;
		try {
			const ownShop = card.product.shop;
			// Свой индекс уже в кэше поиска (карточка грузилась через loadIndex):
			// строка цели даёт exact_model, не делая нового запроса.
			const own = await catalog.loadIndex(ownShop);
			if (`${card.product.shop}:${card.product.sku}` !== requested) return; // A → B
			const target = own?.rows.find((r) => r.product.sku === card!.product.sku) ?? null;
			if (!target) {
				offersState = { kind: 'hidden' };
				offersForIdentity = requested;
				return;
			}
			// К сравнению годятся магазины с catalog-v2 (запись в манифесте);
			// их индексы грузятся по запросу и остаются в общем кэше поиска.
			const otherShops = [...new Set(dashboard.shops.map((s) => s.name))].filter((name) => name !== ownShop);
			const comparable: string[] = [];
			for (const name of otherShops) {
				const binding = await catalog.getSource(name);
				if (binding?.entry) comparable.push(name);
			}
			const indexes = new Map<string, CatalogIndex>();
			for (const name of [ownShop, ...comparable]) {
				const index = await catalog.loadIndex(name).catch(() => null);
				if (`${card.product.shop}:${card.product.sku}` !== requested) return; // A → B
				if (index) indexes.set(name, index);
			}
			const state = partialOffers(target, indexes, [ownShop, ...comparable]);
			offersForIdentity = requested;
			if (!state) offersState = { kind: 'hidden' };
			else if (state.offers.length) offersState = { kind: 'ready', state };
			else offersState = { kind: 'empty', partial: state.partial };
		} catch (e) {
			offersError = e instanceof Error ? e.message : String(e);
			offersForIdentity = requested; // ошибка относится к этому товару — блок видим
		} finally {
			offersLoading = false;
		}
	}
	/** Блок офферов показывается только для товара, чей запрос его собрал;
	 * сбой загрузки виден и без собранного состояния (с «Повторить»). */
	let offersVisible = $derived(
		offersVisibleFor(
			card ? `${card.product.shop}:${card.product.sku}` : null,
			{ ownerIdentity: offersForIdentity, state: offersState, error: offersError }
		)
	);
</script>

<svelte:head><title>{card?.product.title ?? 'История цены'} — skidki</title></svelte:head>

<a href={backHref} class="inline-flex items-center gap-1.5 text-sm font-medium mb-5" style="color:var(--ink-3)">
	<ArrowLeft size={14} /> К скидкам
</a>

{#if loading}
	<div class="flex h-64 items-center justify-center"><span class="h-8 w-8 animate-spin rounded-full border-[3px] border-[var(--line)] border-t-[var(--accent)]"></span></div>
{:else if failed?.kind === 'missing'}
	<div class="rounded-2xl p-12 text-center" style="background:var(--surface); border:1px solid var(--line); color:var(--ink-3)">Товар не найден в каталоге этого магазина.</div>
{:else if failed?.kind === 'unavailable'}
	<div class="rounded-2xl p-12 text-center" style="background:var(--surface); border:1px solid var(--line); color:var(--ink-3)">
		<p>Не удалось загрузить данные о товаре{failed.reason ? ` — ${failed.reason}` : ''}.</p>
		<button class="item-btn" style="margin-top:14px" onclick={() => (retryTick += 1)}>Повторить</button>
	</div>
{:else if card}
	<div class="item-head flex gap-4 mb-6">
		{#if card.product.image}
			<img src={card.product.image} alt={card.product.title} loading="lazy" referrerpolicy="no-referrer" class="h-28 w-28 shrink-0 rounded-2xl object-contain p-3" style="background:var(--surface); border:1px solid var(--line)" />
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex flex-wrap items-center gap-2">
				<span class="meta-pill">{shopLabel(card.product.shop)}</span>
				{#if card.product.brand}<span class="text-xs" style="color:var(--ink-4)">{card.product.brand}</span>{/if}
				{#if card.product.category}<span class="text-xs" style="color:var(--ink-4)">· {card.product.category}</span>{/if}
				{#if card.product.rating && card.product.rating > 0}
					<span class="text-xs font-mono" style="color:var(--ink-3)">★ {card.product.rating.toFixed(1)}{card.product.reviews_count ? ` (${card.product.reviews_count})` : ''}</span>
				{/if}
			</div>
			<h1 class="mt-2 text-xl font-bold tracking-tight leading-tight" style="color:var(--ink)">{card.product.title}</h1>
			{#if view}
				<div style="margin-top:10px">
					{#if view.kind === 'deal' && verdict}
						<VerdictChip {verdict} size="md" />
					{:else}
						<span class="state-pill" data-kind={view.kind}>{view.label}{#if view.kind === 'thin-history' && view.firstSeen} · наблюдаем с {formatDate(view.firstSeen)}{/if}</span>
					{/if}
				</div>
			{/if}
			<div class="mt-3 flex flex-wrap items-baseline gap-3">
				<span class="font-mono text-3xl font-black tracking-tight" style="color:var(--ink)">{formatPrice(card.product.price)}</span>
				{#if view?.kind === 'delisted' && view.lastSeen}
					<span class="text-sm" style="color:var(--ink-4)">цена на {formatDate(view.lastSeen)}</span>
				{/if}
				{#if saving}
					<span class="inline-flex items-center gap-1 text-sm font-semibold px-2.5 py-1 rounded-full" style="background:var(--success-bg); color:var(--success)">
						<ArrowDown size={14} />
						{formatPrice(saving.delta)} (−{Math.round(saving.pct)}%)
					</span>
				{/if}
				{#if baseLine}
					<span class="font-mono text-sm" style="color:var(--ink-4)">обычно {formatPrice(baseLine)}</span>
				{:else if card.product.old_price && card.product.old_price > card.product.price}
					<del class="font-mono text-sm" style="color:var(--ink-4)" title="Зачёркнутая цена магазина">{formatPrice(card.product.old_price)}</del>
				{/if}
			</div>
			<div class="item-actions mt-4 flex flex-wrap gap-2">
				{#if view?.kind !== 'delisted' && card.product.url && card.product.url !== '#'}
					<a href={card.product.url} target="_blank" rel="noopener" class="item-btn primary"><ExternalLink size={14} /> В магазин</a>
				{/if}
				{#if card.source === 'catalog-v2'}
					<button onclick={comparePrices} class="item-btn" disabled={offersLoading}>
						<ArrowRightLeft size={14} /> {offersLoading ? 'Загружаем…' : 'Сравнить цены'}
					</button>
				{/if}
				<button onclick={toggleFav} class="item-btn" class:on={fav}><Heart size={14} fill={fav ? 'currentColor' : 'none'} /> {fav ? 'В избранном' : 'В избранное'}</button>
				<button onclick={shareItem} class="item-btn">{#if copiedItem}<Check size={14} /> Скопировано{:else}<Share2 size={14} /> Поделиться{/if}</button>
				<button onclick={copyLink} class="item-btn">{#if copiedLink}<Check size={14} />{:else}<Copy size={14} />{/if} Ссылка</button>
			</div>
		</div>
	</div>

	{#if advice}
		<section class="advice {advice.tone}">
			<p class="advice-title">{advice.title}</p>
			<p class="advice-text">{advice.text}</p>
		</section>
	{/if}

	{#if offersVisible}
		<section class="rounded-2xl p-5 mb-5" style="background:var(--surface); border:1px solid var(--line)">
			<h2 class="font-bold tracking-tight flex items-center gap-2" style="color:var(--ink)"><ArrowRightLeft size={14} /> Та же комплектация в других магазинах</h2>
			{#if offersError}
				<p class="text-sm mt-2" style="color:var(--bad)">Не удалось загрузить предложения{offersError ? ` — ${offersError}` : ''}.</p>
				<button class="item-btn" style="margin-top:10px" onclick={comparePrices}>Повторить</button>
			{:else if offersState!.kind === 'empty'}
				<p class="text-sm mt-2" style="color:var(--ink-3)">В других магазинах этой комплектации сейчас нет{offersState!.partial ? ' — среди загруженных предложений' : ''}.</p>
			{:else if offersState!.kind === 'ready'}
				{#if offersState!.state.note}
					<p class="text-xs mt-1" style="color:var(--ink-4)">Показаны {offersState!.state.note} — не все магазины каталога загружены.</p>
				{/if}
				<div class="grid gap-2 mt-3">
					{#each offersState!.state.offers as o (o.product.shop + ':' + o.product.sku)}
						<a href={o.product.url} target="_blank" rel="noopener" class="related-row">
							<span class="min-w-0">
								<span class="text-sm font-medium" style="color:var(--ink)">{shopLabel(o.product.shop)}</span>
								{#if o.exact_model}<span class="text-xs ml-2" style="color:var(--ink-4)">· {o.exact_model}</span>{/if}
								{#if o.last_seen}<span class="text-xs ml-2" style="color:var(--ink-4)">· {formatDate(o.last_seen)}</span>{/if}
							</span>
							{#if o.product.price < card!.product.price}
								<span class="text-xs font-semibold px-2 py-0.5 rounded-full" style="background:var(--success-bg); color:var(--success)">−{formatPrice(card!.product.price - o.product.price)}</span>
							{/if}
							<span class="font-mono text-sm font-bold shrink-0" style="color:var(--ink)">{formatPrice(o.product.price)}</span>
						</a>
					{/each}
				</div>
			{/if}
		</section>
	{/if}

	{#if card.stats}
		<section class="stat-grid" style="margin-bottom:20px">
			<div class="stat-card"><p>Обычная цена</p><p style="color:var(--ink)">{view?.basePrice != null ? formatPrice(view.basePrice) : '—'}</p></div>
			<div class="stat-card"><p>Минимум за 35 дней</p><p style="color:var(--success)">{card.stats.min90d != null ? formatPrice(card.stats.min90d) : '—'}</p></div>
			<div class="stat-card"><p>Дней с этой ценой</p><p style="color:var(--ink)">{card.stats.daysAtCurrent ?? '—'}</p></div>
		</section>
	{/if}

	{#if card.points.length}
		<section class="rounded-2xl p-5 mb-5" style="background:var(--surface); border:1px solid var(--line)">
			<h2 class="text-sm font-bold tracking-tight flex items-center gap-2" style="color:var(--ink)"><TrendingDown size={14} /> История цены</h2>
			<div class="mt-4"><PriceChart data={card.points} height={260} labelFormatter={(d) => (d.length >= 10 ? formatDate(d) : d)} /></div>
		</section>

		<section class="rounded-2xl p-5 mb-5" style="background:var(--surface); border:1px solid var(--line)">
			<h2 class="font-bold tracking-tight" style="color:var(--ink)">Последние наблюдения</h2>
			<p class="text-xs mt-1" style="color:var(--ink-4)">Изменение к предыдущей записи · новые сверху</p>
			<div class="overflow-x-auto mt-3">
				<table class="w-full text-left text-sm">
					<thead><tr class="text-xs" style="color:var(--ink-4); border-bottom:1px solid var(--line)"><th class="py-2 font-semibold">Дата</th><th class="font-semibold">Цена</th><th class="font-semibold">Изменение</th></tr></thead>
					<tbody>
						{#each recentPrices(card.recent.length ? card.recent : card.points).reverse() as point}
							<tr style="border-bottom:1px solid var(--paper-2)"><td class="py-3" style="color:var(--ink-3)"><time datetime={point.date}>{formatDate(point.date)}</time></td><td class="font-mono font-medium" style="color:var(--ink)">{formatPrice(point.price)}</td><td class:price-down={point.change !== null && point.change < 0} class:price-up={point.change !== null && point.change > 0} class="font-mono text-sm">{formatChange(point.change)}</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	{#if dealForItem}
	{@const related = relatedDeals(dealForItem, dashboard.deals)}
	{#if related.length}
	<section class="rounded-2xl p-5 mb-5" style="background:var(--surface); border:1px solid var(--line)">
		<h2 class="font-bold tracking-tight" style="color:var(--ink)">Похожие</h2>
		<p class="text-xs mt-1" style="color:var(--ink-4)">Та же группа, похожая цена — сначала та же категория и реальные снижения.</p>
		<div class="grid gap-2 mt-3">
			{#each related as r (r.product.shop + r.product.sku)}<a href="{base}/item?shop={encodeURIComponent(r.product.shop)}&sku={encodeURIComponent(r.product.sku)}" class="related-row"><span class="text-sm font-medium truncate" style="color:var(--ink)">{r.product.title}</span><VerdictChip verdict={verdictOf(r)} /><span class="font-mono text-sm font-bold shrink-0" style="color:var(--ink)">{formatPrice(r.product.price)}</span></a>{/each}
		</div>
	</section>
	{/if}
	{/if}
{/if}

<style>
@media (max-width: 640px) {
	.item-head { flex-direction: column; }
	.item-head img { width: 100%; height: 180px; }
	.item-head :global(.item-actions) { display: grid !important; grid-template-columns: 1fr 1fr; }
	.item-btn { justify-content: center; }
}
.item-btn {
	display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 16px;
	border-radius: 999px; font-size: 13px; font-weight: 600; text-decoration: none;
	background: var(--surface); border: 1px solid var(--line); color: var(--ink-2);
}
.item-btn:hover { border-color: var(--ink-3); color: var(--ink); }
.item-btn.primary { background: var(--ink); border-color: var(--ink); color: var(--on-ink); }
.item-btn.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.state-pill {
	display: inline-flex; align-items: center; gap: 6px;
	font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 999px;
	background: var(--paper-2); color: var(--ink-3); border: 1px solid var(--line);
}
.state-pill[data-kind='below'] { background: var(--success-bg); color: var(--success); border-color: color-mix(in srgb, var(--success) 22%, transparent); }
.state-pill[data-kind='above'] { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-line); }
.state-pill[data-kind='delisted'] { background: var(--bad-bg); color: var(--bad); border-color: var(--bad-line); }
.advice { border-radius: var(--radius); padding: 16px 20px; margin-bottom: 20px; border: 1px solid; }
.advice-title { font-weight: 700; font-size: 16px; letter-spacing: -0.01em; }
.advice-text { font-size: 14px; margin-top: 4px; opacity: 0.9; }
.advice.good { background: var(--success-bg); color: var(--success); border-color: color-mix(in srgb, var(--success) 22%, transparent); }
.advice.warn { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-line); }
.advice.bad { background: var(--bad-bg); color: var(--bad); border-color: var(--bad-line); }
.advice.muted { background: var(--paper-2); color: var(--ink-3); border-color: var(--line); }
.related-row {
	display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px;
	padding: 12px; border-radius: 12px; border: 1px solid var(--line); text-decoration: none;
}
.related-row:hover { border-color: var(--ink-4); }
</style>
