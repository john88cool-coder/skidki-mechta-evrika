<script lang="ts">
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import { onMount } from 'svelte';
	import { theme } from '$lib/stores/theme.svelte';
	import { favorites } from '$lib/stores/favorites.svelte';
	import { compare } from '$lib/stores/compare.svelte';
	import { dashboard, startAutoRefresh } from '$lib/stores/data.svelte';

	let { children } = $props();
	let paletteOpen = $state(false);

	onMount(() => {
		theme.init();
		favorites.init();
		compare.init();
		dashboard.refresh();
		const onKey = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); paletteOpen = !paletteOpen; }
			if (e.key === '/' && !paletteOpen && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement) && !(e.target instanceof HTMLSelectElement)) {
				// quick focus for search fields that use "/" convention
				e.preventDefault(); paletteOpen = true;
			}
		};
		window.addEventListener('keydown', onKey);
		const stop = startAutoRefresh(30_000);
		return () => { window.removeEventListener('keydown', onKey); stop(); };
	});
</script>

<a href="#main-content" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-[var(--ink)] focus:text-white focus:px-4 focus:py-2 focus:text-sm">К содержимому</a>
<div class="min-h-screen flex flex-col">
	<Header onsearch={() => (paletteOpen = true)} />
	<main class="app-main flex-1 w-full" id="main-content">
		{#if dashboard.error}
			<div class="mb-4 rounded-2xl px-4 py-3 text-sm flex items-center gap-2" style="background:var(--accent-2); border:1px solid color-mix(in srgb, var(--accent) 22%, transparent); color:var(--accent-ink)">
				Не удалось загрузить данные: {dashboard.error}. Обновится автоматически.
			</div>
		{/if}
		{@render children()}
		<footer class="app-footer">
			<span><strong style="color:var(--ink)">skidki</strong> · Наблюдаем за ценами в Казахстане · 6 магазинов · история каждой цены</span>
			<span>₸ KZT · Актуальную цену и наличие проверяйте в магазине</span>
		</footer>
	</main>
</div>

<CommandPalette open={paletteOpen} onclose={() => (paletteOpen = false)} />
