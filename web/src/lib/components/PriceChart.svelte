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
				axisLine: { lineStyle: { color: '#334155' } },
				axisTick: { show: false },
				axisLabel: { color: '#94a3b8', fontSize: 11 }
			},
			yAxis: {
				type: 'value',
				scale: true,
				axisLine: { show: false },
				splitLine: { lineStyle: { color: '#1e293b' } },
				axisLabel: {
					color: '#94a3b8',
					fontSize: 11,
					formatter: (v: number) => `${Math.round(v / 1000)}k`
				}
			},
			series: [
				{
					type: 'line',
					data: prices,
					smooth: true,
					showSymbol: data.length <= 60,
					symbol: 'circle',
					symbolSize: 5,
					lineStyle: { color: '#f59e0b', width: 2 },
					itemStyle: { color: '#f59e0b' },
					markLine: {
						silent: true,
						symbol: 'none',
						lineStyle: { color: '#10b981', type: 'dashed', width: 1 },
						label: { color: '#10b981', fontSize: 10, formatter: 'минимум' },
						data: [{ yAxis: lowest }]
					},
					areaStyle: {
						color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
							{ offset: 0, color: 'rgba(245, 158, 11, 0.30)' },
							{ offset: 1, color: 'rgba(245, 158, 11, 0)' }
						])
					}
				}
			],
			tooltip: {
				trigger: 'axis',
				backgroundColor: '#1e293b',
				borderColor: '#334155',
				textStyle: { color: '#f1f5f9', fontSize: 12 },
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

