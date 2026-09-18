<script lang="ts">
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import { onMount } from 'svelte';
	import { dashboard, startAutoRefresh } from '$lib/stores/data.svelte';

	let { children } = $props();

	onMount(() => {
		dashboard.refresh();
		// Автообновление: страница живёт открытой, сводки приходят каждые 2 ч.
		return startAutoRefresh(30_000);
	});
</script>

<div class="min-h-screen bg-slate-950">
	<Header />
	<main class="mx-auto max-w-7xl px-4 py-6">
		{#if dashboard.error}
			<div class="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
				Не удалось загрузить данные: {dashboard.error}. Панель обновится автоматически.
			</div>
		{/if}
		{@render children()}
	</main>
</div>
