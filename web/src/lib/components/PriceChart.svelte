<script lang="ts">
	import * as echarts from 'echarts';
	import { theme } from '$lib/stores/theme.svelte';
	import { formatPrice } from '$lib/utils/format';
	import type { PricePoint } from '$lib/types';

	interface Props {
		data?: PricePoint[];
		height?: number;
		labelFormatter?: (label: string) => string;
	}
	let { data = [], height = 200, labelFormatter }: Props = $props();
	let chartEl: HTMLDivElement | undefined = $state();
	let chart: echarts.ECharts | undefined;

	function buildOption(): echarts.EChartsOption {
		const dark = theme.current === 'dark';
		const labels = data.map((p) => (labelFormatter ? labelFormatter(p.date) : p.date));
		const prices = data.map((p) => p.price);
		const lowest = prices.length ? Math.min(...prices) : 0;
		const ink = dark ? '#8ea69d' : '#5a6b64';
		const gridLine = dark ? '#1e2e28' : '#ede9e3';
		const accent = dark ? '#ff6b4a' : '#ff3b1f';
		return {
			backgroundColor: 'transparent',
			grid: { top: 14, right: 14, bottom: 28, left: 62 },
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: labels,
				axisLine: { lineStyle: { color: dark ? '#2a3d34' : '#ddd8d1' } },
				axisTick: { show: false },
				axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrains Mono' }
			},
			yAxis: {
				type: 'value',
				scale: true,
				axisLine: { show: false },
				splitLine: { lineStyle: { color: gridLine } },
				axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrains Mono', formatter: (v: number) => `${Math.round(v / 1000)}k` }
			},
			series: [
				{
					type: 'line',
					data: prices,
					step: 'end',
					showSymbol: data.length <= 60,
					symbol: 'circle',
					symbolSize: 4,
					lineStyle: { color: accent, width: 2.2 },
					itemStyle: { color: accent, borderColor: dark ? '#0c1210' : '#fff', borderWidth: 1.5 },
					markLine: {
						silent: true,
						symbol: 'none',
						lineStyle: { color: dark ? '#3a5a4a' : '#b8c8bd', type: 'dashed', width: 1 },
						label: { color: ink, fontSize: 10, formatter: 'минимум' },
						data: [{ yAxis: lowest }]
					},
					areaStyle: {
						color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
							{ offset: 0, color: dark ? 'rgba(255,91,54,0.18)' : 'rgba(255,59,31,0.12)' },
							{ offset: 1, color: 'rgba(255,59,31,0)' }
						])
					}
				}
			],
			tooltip: {
				trigger: 'axis',
				backgroundColor: dark ? '#1a2e26' : '#fff',
				borderColor: dark ? '#2a3d34' : '#e8e2da',
				borderWidth: 1,
				padding: [8, 10],
				textStyle: { color: dark ? '#eef4f0' : '#0e1a15', fontSize: 12 },
				formatter: (params: unknown) => {
					const p = Array.isArray(params) ? (params as any[])[0] : params as any;
					return `${p.name}<br/><b>${formatPrice(p.value as number)}</b>`;
				}
			}
		};
	}

	$effect(() => {
		if (!chartEl) return;
		chart = chart ?? echarts.init(chartEl);
		chart.setOption(buildOption(), true);
	});
	$effect(() => {
		// Rebuild on theme toggle
		void theme.current;
		if (chart) chart.setOption(buildOption(), true);
	});
	$effect(() => {
		if (!chartEl) return;
		const onResize = () => chart?.resize();
		window.addEventListener('resize', onResize);
		return () => {
			window.removeEventListener('resize', onResize);
			chart?.dispose();
			chart = undefined;
		};
	});
</script>

<div bind:this={chartEl} style="height: {height}px" class="w-full"></div>
