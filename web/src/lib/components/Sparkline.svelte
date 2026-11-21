<script lang="ts">
	import type { PricePoint } from '$lib/types';
	import { sparkline } from '$lib/utils/sparkline';

	/** Мини-график цены в карточке: видно без клика, как цена шла последние недели. */
	interface Props { points: PricePoint[]; label?: string }
	let { points, label = 'График цены' }: Props = $props();
	const W = 240;
	const H = 40;
	let path = $derived(sparkline(points, W, H));
</script>

{#if path}
	<svg class="spark {path.trend}" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="{label}: {path.days} дн. наблюдений">
		<path class="spark-area" d={path.area} />
		<path class="spark-line" d={path.line} vector-effect="non-scaling-stroke" />
	</svg>
{/if}

<style>
	.spark { display: block; width: 100%; height: 40px; color: var(--ink-4); }
	.spark.down { color: var(--success); }
	.spark.up { color: var(--accent); }
	.spark-area { fill: currentColor; opacity: 0.1; }
	.spark-line { fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linejoin: round; }
</style>
