<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	/** Раздел «Топ» слит с каталогом: старые ссылки ведут на «Реально подешевело». */
	const target = `${base}/deals?v=real`;
	onMount(() => {
		goto(target, { replaceState: true });
	});
</script>

<svelte:head>
	<title>Реально подешевело — skidki</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<p class="page-description">Раздел переехал: <a href={target}>реально подешевело в каталоге</a>.</p>
