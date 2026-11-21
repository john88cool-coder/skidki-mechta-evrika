<script lang="ts">
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	/** Сравнение убрано: сравнивать одну модель в разных магазинах будет страница товара. */
	const target = `${base}/favorites`;
	onMount(() => {
		goto(target, { replaceState: true });
	});
</script>

<svelte:head>
	<title>Избранное — skidki</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<p class="page-description">Раздел «Сравнение» убран. Отложенные товары — в <a href={target}>избранном</a>.</p>
