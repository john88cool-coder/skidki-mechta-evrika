<script lang="ts">
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import { onMount } from 'svelte';
	import { theme } from '$lib/stores/theme.svelte';
	import { dashboard, startAutoRefresh } from '$lib/stores/data.svelte';

	let { children } = $props();

	onMount(() => {
		theme.init();
		dashboard.refresh();
		// Автообновление: страница живёт открытой, сводки приходят каждые 2 ч.
		return startAutoRefresh(30_000);
	});
</script>

<a href="#main-content" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-white focus:p-3">К содержимому</a>
<div class="min-h-screen">
	<Header />
	<main class="app-main" id="main-content">
		{#if dashboard.error}
			<div class="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700">
				Не удалось загрузить данные: {dashboard.error}. Панель обновится автоматически.
			</div>
		{/if}
		{@render children()}
		<footer class="app-footer"><span>skidki · Наблюдаем за ценами в Казахстане</span><span>₸ KZT · Актуальную цену и наличие проверяйте в магазине</span></footer>
	</main>
</div>
