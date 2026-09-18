<script lang="ts">
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import { onMount } from 'svelte';
	import { fetchDashboard, startAutoRefresh, stopAutoRefresh } from '$lib/stores/data';

	let { children } = $props();

	onMount(() => {
		fetchDashboard();
		startAutoRefresh();
		return stopAutoRefresh;
	});
</script>

<div class="min-h-screen bg-slate-950">
	<Header />
	<main class="mx-auto max-w-7xl px-4 py-6">
		{@render children()}
	</main>
</div>
