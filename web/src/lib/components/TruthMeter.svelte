<script lang="ts">
	import { base } from '$app/paths';
	import { VERDICT_LABELS, VERDICT_ORDER, type VerdictKind } from '$lib/utils/verdict';

	/** «Шкала правды»: во что превращаются скидки на ценниках после проверки историей. */
	interface Props { counts: Record<VerdictKind, number>; total: number }
	let { counts, total }: Props = $props();
	let pct = (n: number) => (total ? (n / total) * 100 : 0);
</script>

<div class="truth">
	<p class="truth-title">Из {total} скидок на ценниках</p>
	<div class="truth-bar" role="img" aria-label={VERDICT_ORDER.map((k) => `${VERDICT_LABELS[k]}: ${counts[k]}`).join(', ')}>
		{#each VERDICT_ORDER as k (k)}
			{#if counts[k]}<i class={k} style="width:{pct(counts[k])}%"></i>{/if}
		{/each}
	</div>
	<ul class="truth-legend">
		{#each VERDICT_ORDER as k (k)}
			<li><a href="{base}/deals?v={k}"><span class="dot {k}"></span>{VERDICT_LABELS[k]} <b>{counts[k]}</b></a></li>
		{/each}
	</ul>
</div>
