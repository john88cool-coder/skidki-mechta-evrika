<script lang="ts">
	import * as echarts from 'echarts';
	import { formatPrice } from '$lib/utils/format';
	import type { PricePoint } from '$lib/types';

	interface Props {
		data?: PricePoint[];
		height?: number;
		/** Подпись оси X: реальные даты (история) или номера точек. */
		labelFormatter?: (label: string) => string;
	}

	let { data = [], height = 200, labelFormatter }: Props = $props();

	let chartEl: HTMLDivElement | undefined = $state();
	let chart: echarts.ECharts | undefined;

	function buildOption(): echarts.EChartsOption {
		const labels = data.map((p) => (labelFormatter ? labelFormatter(p.date) : p.date));
		const prices = data.map((p) => p.price);
		const lowest = prices.length ? Math.min(...prices) : 0;

		return {
			backgroundColor: 'transparent',
			grid: { top: 16, right: 16, bottom: 28, left: 68 },
			xAxis: {
				type: 'category',
				boundaryGap: false,
				data: labels,
				axisLine: { lineStyle: { color: '#d9e1d5' } },
				axisTick: { show: false },
				axisLabel: { color: '#657263', fontSize: 11 }
			},
			yAxis: {
				type: 'value',
				scale: true,
				axisLine: { show: false },
				splitLine: { lineStyle: { color: '#edf1e8' } },
				axisLabel: {
					color: '#657263',
					fontSize: 11,
					formatter: (v: number) => `${Math.round(v / 1000)}k`
				}
			},
			series: [
				{
					type: 'line',
					data: prices,
					step: 'end',
					showSymbol: data.length <= 60,
					symbol: 'circle',
					symbolSize: 5,
					lineStyle: { color: '#2a6b50', width: 2 },
					itemStyle: { color: '#2a6b50' },
					markLine: {
						silent: true,
						symbol: 'none',
						lineStyle: { color: '#40845c', type: 'dashed', width: 1 },
						label: { color: '#40845c', fontSize: 10, formatter: 'минимум' },
						data: [{ yAxis: lowest }]
					},
					areaStyle: {
						color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
							{ offset: 0, color: 'rgba(42, 107, 80, 0.14)' },
							{ offset: 1, color: 'rgba(42, 107, 80, 0)' }
						])
					}
				}
			],
			tooltip: {
				trigger: 'axis',
				backgroundColor: '#edf1e8',
				borderColor: '#d9e1d5',
				textStyle: { color: '#263c2e', fontSize: 12 },
				formatter: (params: any) => {
					const point = Array.isArray(params) ? params[0] : params;
					return `${point.name}<br/><b>${formatPrice(point.value as number)}</b>`;
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

