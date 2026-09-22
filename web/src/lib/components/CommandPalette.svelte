<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { dashboard } from '$lib/stores/data.svelte';
	import { shopLabel, formatPrice } from '$lib/utils/format';
	import { Search, Tag, LayoutGrid, Activity, Heart, X } from '@lucide/svelte';

	interface Props { open: boolean; onclose: () => void }
	let { open, onclose }: Props = $props();

	let q = $state('');
	let inputEl: HTMLInputElement | undefined = $state();
	let selected = $state(0);

	const staticItems = [
		{ label: 'Обзор', href: `${base}/`, icon: LayoutGrid, kbd: 'G H' },
		{ label: 'Каталог', href: `${base}/deals`, icon: Tag, kbd: 'G C' },
		{ label: 'Магазины', href: `${base}/shops`, icon: Activity, kbd: 'G S' },
		{ label: 'Избранное', href: `${base}/favorites`, icon: Heart, kbd: 'G F' }
	];

	let results = $derived.by(() => {
		const needle = q.trim().toLowerCase();
		if (!needle) return dashboard.deals.slice(0, 8);
		return dashboard.deals.filter(d =>
			d.product.title.toLowerCase().includes(needle) ||
			(d.product.brand ?? '').toLowerCase().includes(needle) ||
			d.product.shop.toLowerCase().includes(needle)
		).slice(0, 8);
	});

	let allItems = $derived.by(() => {
		if (q.trim()) return results.map(r => ({ kind: 'deal' as const, deal: r }));
		return [
			...staticItems.map(s => ({ kind: 'nav' as const, nav: s })),
			...results.map(r => ({ kind: 'deal' as const, deal: r }))
		];
	});

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') { e.preventDefault(); onclose(); }
		if (e.key === 'ArrowDown') { e.preventDefault(); selected = Math.min(selected + 1, allItems.length - 1); }
		if (e.key === 'ArrowUp') { e.preventDefault(); selected = Math.max(selected - 1, 0); }
		if (e.key === 'Enter') { e.preventDefault(); activate(selected); }
	}
	function activate(idx: number) {
		const item = allItems[idx];
		if (!item) return;
		if (item.kind === 'nav') goto(item.nav.href);
		else goto(`${base}/item?shop=${encodeURIComponent(item.deal.product.shop)}&sku=${encodeURIComponent(item.deal.product.sku)}`);
		onclose();
	}

	$effect(() => {
		if (open) {
			q = ''; selected = 0;
			requestAnimationFrame(() => inputEl?.focus());
		}
	});
	$effect(() => { void q; selected = 0; });
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-start justify-center pt-[18vh] p-4" onclick={(e) => { if (e.target === e.currentTarget) onclose(); }} onkeydown={onKeydown}>
		<div class="absolute inset-0 bg-[#0e1a15]/45 backdrop-blur-[6px]" aria-hidden="true"></div>
		<div class="relative w-full max-w-[640px] rounded-[18px] overflow-hidden shadow-[0_16px_48px_rgba(0,0,0,0.22)]" style="background:var(--surface); border:1px solid var(--line)">
			<div class="flex items-center gap-3 px-4 h-[56px] border-b" style="border-color:var(--line)">
				<Search size={18} style="color:var(--ink-4)" />
				<input
					bind:this={inputEl}
					bind:value={q}
					placeholder="Поиск товаров, брендов, магазинов…"
					class="flex-1 h-full bg-transparent outline-none text-[15px]"
					style="color:var(--ink)"
					aria-label="Поиск"
				/>
				<button onclick={onclose} class="icon-btn !w-7 !h-7" aria-label="Закрыть"><X size={14} /></button>
			</div>
			<div class="max-h-[380px] overflow-auto p-2">
				{#each allItems as item, i (i)}
					<button
						onclick={() => activate(i)}
						class="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors {i === selected ? 'text-white' : ''}"
						style={i === selected ? 'background:var(--ink); color:var(--on-ink)' : 'color:var(--ink-2)'}
					>
						{#if item.kind === 'nav'}
							<item.nav.icon size={16} />
							<span class="font-medium">{item.nav.label}</span>
							<span class="ml-auto font-mono text-[11px] opacity-60">{item.nav.kbd}</span>
						{:else}
							<span class="shrink-0 text-[11px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded" style="background:{i===selected?'rgba(255,255,255,0.15)':'var(--paper-2)'}; color:{i===selected?'white':'var(--ink-3)'}">{shopLabel(item.deal.product.shop)}</span>
							<span class="truncate flex-1 font-medium">{item.deal.product.title}</span>
							<span class="font-mono font-bold shrink-0" style="color:{i===selected?'white':'var(--accent)'}">{formatPrice(item.deal.product.price)}</span>
						{/if}
					</button>
				{:else}
					<p class="text-sm text-center py-8" style="color:var(--ink-4)">Ничего не нашлось</p>
				{/each}
			</div>
			<div class="flex items-center gap-2 px-4 py-2.5 text-[11px] border-t" style="border-color:var(--line); color:var(--ink-4); background:var(--paper-2)">
				<span class="font-mono">↵</span> открыть · <span class="font-mono">↑↓</span> навигация · <span class="font-mono">Esc</span> закрыть
				<span class="ml-auto hidden sm:inline">Нажми <span class="font-mono font-bold px-1.5 py-0.5 rounded" style="background:var(--surface); border:1px solid var(--line)">⌘K</span> в любой момент</span>
			</div>
		</div>
	</div>
{/if}
