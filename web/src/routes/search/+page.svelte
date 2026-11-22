<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { untrack } from 'svelte';
	import { catalog } from '$lib/stores/catalog.svelte';
	import { searchCatalog, gatherRows, type GatherResult } from '$lib/utils/catalog-search';
	import { shopLabel, formatPrice } from '$lib/utils/format';
	import { Search, SearchX, ArrowRight, RefreshCw } from '@lucide/svelte';
	import type { CatalogRow } from '$lib/types';

	const PAGE = 24;

	let q = $state(untrack(() => page.url.searchParams.get('q') ?? ''));
	let shown = $state(PAGE);
	// Генерация запроса: запоздавший результат предыдущего не замещает новый.
	let gen = $state(0);
	let loading = $state(false);
	let started = $state(false);
	let rows = $state<CatalogRow[]>([]);
	let failed = $state<string[]>([]);
	let showcaseOnly = $state<string[]>([]);

	async function runSearch() {
		const g = ++gen;
		loading = true;
		started = true;
		shown = PAGE;
		rows = [];
		failed = [];
		showcaseOnly = [];
		try {
			const apply = (res: GatherResult) => {
				if (g !== gen) return; // начат новый запрос — частичный результат устарел
				rows = res.rows;
				failed = res.failed;
				showcaseOnly = res.showcaseOnly;
			};
			const res = await gatherRows(catalog, { concurrency: 3, onPartial: apply });
			apply(res);
		} catch (e) {
			if (g !== gen) return;
			failed = [...failed, 'источники каталога'];
		} finally {
			if (g === gen) loading = false;
		}
	}

	function submit(e: SubmitEvent) {
		e.preventDefault();
		const trimmed = q.trim();
		const target = `${base}/search${trimmed ? `?${new URLSearchParams({ q: trimmed })}` : ''}`;
		if (target === page.url.pathname + page.url.search) void runSearch();
		else void goto(target);
	}

	// Поиск начинается с действия пользователя: переход на /search?q=… или отправка формы.
	let lastUrlQ = untrack(() => page.url.searchParams.get('q') ?? '');
	$effect(() => {
		const urlQ = page.url.searchParams.get('q') ?? '';
		if (urlQ === lastUrlQ) return;
		lastUrlQ = urlQ;
		q = urlQ;
		if (urlQ) void runSearch();
	});
	if (untrack(() => lastUrlQ)) void runSearch();

	let results = $derived.by(() => {
		const needle = q.trim();
		if (!needle) return [];
		return searchCatalog(rows, needle, shown);
	});
	let total = $derived.by(() => {
		const needle = q.trim();
		if (!needle) return 0;
		return searchCatalog(rows, needle, Infinity).length;
	});
	let canMore = $derived(results.length < total);
	let finished = $derived(started && !loading);
</script>

<svelte:head><title>Поиск товара — skidki</title></svelte:head>

<div class="mx-auto max-w-[880px] px-4 py-8">
	<p class="page-eyebrow">Поиск</p>
	<h1 class="page-heading">Проверить <em>товар</em></h1>
	<p class="page-description">
		Название, модель, SKU или ссылка на товар — проверим по полному каталогу и истории цены.
	</p>

	<form class="search-form mt-6" onsubmit={submit}>
		<label class="search-wrap">
			<Search size={16} />
			<input
				type="search"
				bind:value={q}
				name="q"
				aria-label="Название, модель, SKU или ссылка"
				placeholder="Например: Demo Phone 256, A:17 или ссылка на товар…"
			/>
		</label>
		<button class="search-btn" type="submit">Найти</button>
	</form>

	{#if loading}
		<p class="search-status" role="status">Ищем ещё в магазинах…</p>
	{/if}

	{#if showcaseOnly.length && (started || results.length)}
		<p class="search-note" role="note">
			{shopLabel(showcaseOnly[0])}{#if showcaseOnly.length > 1} и ещё {showcaseOnly.length - 1}{/if}:
			Доступны только товары витрины
		</p>
	{/if}

	{#if failed.length}
		<p class="search-note warn" role="alert">
			Не удалось загрузить: {failed.map(shopLabel).join(', ')}.<br />
			<button class="retry-btn" type="button" onclick={runSearch}><RefreshCw size={13} /> Повторить</button>
		</p>
	{/if}

	{#if results.length}
		<p class="found-pill mt-6"><span>Найдено</span><strong>{total}</strong></p>
		<ul class="search-results">
			{#each results as r (r.product.shop + r.product.sku)}
				<li>
					<a
						class="search-row"
						href="{base}/item?shop={encodeURIComponent(r.product.shop)}&sku={encodeURIComponent(r.product.sku)}"
					>
						<span class="shrink-0 text-[11px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded" style="background:var(--paper-2); color:var(--ink-3)">{shopLabel(r.product.shop)}</span>
						<span class="truncate flex-1 font-medium">{r.product.title}</span>
						{#if !r.product.in_stock}<span class="text-[11px]" style="color:var(--ink-4)">нет в наличии</span>{/if}
						<span class="font-mono font-bold shrink-0" style="color:var(--accent)">{formatPrice(r.product.price)}</span>
						<ArrowRight size={14} class="shrink-0" style="color:var(--ink-4)" />
					</a>
				</li>
			{/each}
		</ul>
		{#if canMore}
			<button class="more-btn mt-4" type="button" onclick={() => (shown += PAGE)}>
				Показать ещё · осталось {total - results.length}
			</button>
		{/if}
	{:else if finished && q.trim() && !failed.length}
		<div class="empty-state mt-8">
			<SearchX size={28} style="color:var(--ink-4)" />
			<p style="color:var(--ink-3)">Ничего не нашлось. Попробуйте название, модель или SKU целиком.</p>
		</div>
	{:else if finished && q.trim() && failed.length && !rows.length}
		<div class="empty-state mt-8">
			<p style="color:var(--ink-3)">Результаты недоступны — каталог не загрузился. Попробуйте повторить.</p>
		</div>
	{/if}
</div>

<style>
	.search-form {
		display: flex;
		gap: 0.5rem;
		align-items: stretch;
	}
	.search-form .search-wrap {
		flex: 1;
	}
	.search-btn {
		border-radius: 12px;
		padding: 0 1.25rem;
		font-weight: 600;
		background: var(--ink);
		color: var(--on-ink);
	}
	.search-status {
		margin-top: 1rem;
		font-size: 0.85rem;
		color: var(--ink-4);
	}
	.search-note {
		margin-top: 1rem;
		font-size: 0.85rem;
		color: var(--ink-3);
	}
	.search-note.warn {
		color: var(--accent-ink);
	}
	.retry-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		margin-top: 0.35rem;
		font-size: 0.8rem;
		font-weight: 600;
		padding: 0.2rem 0.7rem;
		border-radius: 999px;
		border: 1px solid var(--line);
		color: var(--ink-2);
	}
	.search-results {
		margin-top: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.search-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.65rem 0.75rem;
		border-radius: 12px;
		border: 1px solid var(--line);
		font-size: 0.9rem;
		color: var(--ink-2);
	}
	.search-row:hover {
		background: var(--paper-2);
	}
</style>
