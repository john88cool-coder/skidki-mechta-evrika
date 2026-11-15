<script lang="ts">
	import type { Verdict } from '$lib/utils/verdict';
	import { ShieldCheck, TriangleAlert, TrendingUp, Ban, Hourglass } from '@lucide/svelte';

	interface Props { verdict: Verdict; size?: 'sm' | 'md' }
	let { verdict, size = 'sm' }: Props = $props();
	const ICONS = { honest: ShieldCheck, inflated: TriangleAlert, pumped: TrendingUp, painted: Ban, unknown: Hourglass };
	let Icon = $derived(ICONS[verdict.kind]);
</script>

<span class="verdict-chip {verdict.kind} {size}" title={verdict.hint}>
	<Icon size={size === 'md' ? 14 : 12} aria-hidden="true" />{verdict.label}
</span>
