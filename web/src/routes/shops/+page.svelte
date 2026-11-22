<script lang="ts">
	import { base } from '$app/paths';
	import { dashboard } from '$lib/stores/data.svelte';
	import { catalog } from '$lib/stores/catalog.svelte';
	import ShopStatusCard from '$lib/components/ShopStatusCard.svelte';
	import { formatPrice, formatDate } from '$lib/utils/format';
	import { verdictOf, realRank, isReal } from '$lib/utils/verdict';
	import { qualitySummary, type CatalogQuality, type QualitySummary } from '$lib/utils/quality';
	import type { ShopSourceBinding } from '$lib/utils/catalog-source';
	import type { CatalogManifestEntry, Deal, ShopStatus } from '$lib/types';
	import { RefreshCw } from '@lucide/svelte';

	/** Записи манифеста с качеством (задача 7); манифесты Stage 2 без quality — как v1. */
	type EntryWithQuality = CatalogManifestEntry & { quality?: CatalogQuality };

	/** Источники каталога: у выбранной стороны local замещает cloud ровно один раз
	 * (семантика pinned тестом задачи 3); «Обновить» перечитывает их вместе со срезом. */
	let sources = $state<Map<string, ShopSourceBinding>>(new Map());
	let sourcesLoaded = $state(false);
	$effect(() => {
		void dashboard.data; // автообновление и кнопка «Обновить» подтягивают и манифесты
		let cancelled = false;
		catalog.refreshSources()
			.then((m) => {
				if (cancelled) return;
				sources = new Map(m);
				sourcesLoaded = true;
			})
			.catch(() => {
				if (!cancelled) sourcesLoaded = true;
			});
		return () => {
			cancelled = true;
		};
	});

	interface ShopRow {
		shop: ShopStatus;
		summary: QualitySummary | null;
		share: number | null;
		/** Порядковое место — только там, где доля посчитана по всему каталогу v2. */
		rank: number | null;
		crawlAt: string | null;
		real: Deal[];
	}

	let rows = $derived.by<ShopRow[]>(() => {
		const list: (Omit<ShopRow, 'rank'> & { rankable: boolean })[] = dashboard.shops.map((shop) => {
			const deals = dashboard.deals.filter((d) => d.product.shop === shop.name);
			const claimed = deals.filter((d) => d.drop_pct);
			const checked = claimed.filter((d) => verdictOf(d).kind !== 'unknown');
			const painted = checked.filter((d) => verdictOf(d).kind === 'painted').length;
			const real = deals
				.filter((d) => isReal(verdictOf(d).kind))
				.sort((a, b) => realRank(b) - realRank(a));
			const binding = sources.get(shop.name) ?? null;
			const entry = (binding?.entry ?? null) as EntryWithQuality | null;
			// Качество — из манифеста выбранной стороны; витрина — только выборка v1.
			const summary = sourcesLoaded
				? qualitySummary(entry?.quality ?? null, entry?.quality ? null : { claimed: claimed.length, checked: checked.length, painted })
				: null;
			const crawlAt = binding?.last_crawl ?? shop.last_crawl;
			const share = summary?.paintedShare ?? null;
			// Несопоставимые выборки (витрина или пусто) не получают порядкового места.
			const rankable = summary?.state === 'checked';
			return { shop, summary, share, rankable, crawlAt, real };
		});
		// Честные — выше: сначала сравнимые доли, затем несопоставимые выборки.
		list.sort(
			(a, b) =>
				(a.rankable ? 0 : 1) - (b.rankable ? 0 : 1) || (a.share ?? 2) - (b.share ?? 2)
		);
		let rank = 0;
		return list.map(({ rankable, ...row }) => ({ ...row, rank: rankable ? ++rank : null }));
	});
</script>

<svelte:head><title>Магазины — skidki</title></svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4 mb-6">
	<div>
		<p class="page-eyebrow">Источники</p>
		<h1 class="page-heading">Честность <em>магазинов</em></h1>
		<p class="page-description">
			Какая доля скидок на ценниках подтверждается историей цены и сколько товаров в магазине реально подешевело. Честные — выше.
			<a href="{base}/methodology">Как мы считаем</a>
		</p>
	</div>
	<button onclick={() => dashboard.refresh()} class="reset-btn">
		<RefreshCw size={14} class={dashboard.loading ? 'animate-spin' : ''} /> Обновить
	</button>
</div>

<div class="grid gap-4">
	{#each rows as row (row.shop.name)}
		<div class="shop-block">
			{#if row.rank !== null}
				<div class="shop-rank">{row.rank}</div>
			{/if}
			<div class="min-w-0 flex-1">
				<ShopStatusCard shop={row.shop} />
				<div class="shop-stats">
					<div class="stat">
						<p>Проверено</p>
						{#if row.summary}
							<p class="big" class:long={row.summary.state === 'empty'}>{row.summary.text}</p>
							<p class="sub">
								{row.summary.sample}{#if row.crawlAt} · обход {formatDate(row.crawlAt)}{/if}{#if row.summary.checked} · нарисовано {row.summary.painted} из {row.summary.checked}{/if}
							</p>
						{:else}
							<p class="big">—</p>
						{/if}
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
	.stat .big.long { font-family: inherit; font-size: 14px; line-height: 1.35; }
	.stat .big.good { color: var(--success); }
	.stat .sub { font-size: 12px; color: var(--ink-4); margin-top: 2px; }
	.stat .sub a { color: var(--ink-3); text-decoration: none; }
	.stat .sub a:hover { color: var(--ink); }
	.page-description a { color: var(--ink-3); text-decoration: underline; text-underline-offset: 3px; }
	.page-description a:hover { color: var(--ink); }
	.best { display: inline-block; margin-top: 4px; font-family: var(--font-mono); font-size: 14px; color: var(--ink); text-decoration: none; }
	.best b { color: var(--success); }
	.best:hover { text-decoration: underline; text-underline-offset: 3px; }
	@media (max-width: 640px) {
		.shop-block { padding: 14px; gap: 10px; }
		.shop-rank { display: none; }
		.shop-stats { grid-template-columns: minmax(0, 1fr); }
	}
</style>
