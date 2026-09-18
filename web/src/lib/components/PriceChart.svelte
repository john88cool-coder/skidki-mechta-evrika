<script lang="ts">
	import { onMount } from 'svelte';
	import * as echarts from 'echarts';
	import type { PricePoint } from '$lib/types';

	interface Props {
		data?: PricePoint[];
		height?: number;
	}

	let { data = [], height = 200 }: Props = $props();

	let chartEl: HTMLDivElement;

	onMount(() => {
		const chart = echarts.init(chartEl);
		
		const option = {
			backgroundColor: 'transparent',
			grid: { top: 20, right: 20, bottom: 30, left: 60 },
			xAxis: {
				type: 'category',
				data: data.map(d => d.date),
				axisLine: { lineStyle: { color: '#334155' } },
				axisLabel: { color: '#94a3b8' }
			},
			yAxis: {
				type: 'value',
				axisLine: { show: false },
				splitLine: { lineStyle: { color: '#1e293b' } },
				axisLabel: { 
					color: '#94a3b8',
					formatter: (v: number) => (v / 1000).toFixed(0) + 'k'
				}
			},
			series: [{
				type: 'line',
				data: data.map(d => d.price),
				smooth: true,
				symbol: 'circle',
				symbolSize: 6,
				lineStyle: { color: '#f59e0b', width: 2 },
				itemStyle: { color: '#f59e0b' },
				areaStyle: {
					color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
						{ offset: 0, color: 'rgba(245, 158, 11, 0.3)' },
						{ offset: 1, color: 'rgba(245, 158, 11, 0)' }
					])
				}
			}],
			tooltip: {
				trigger: 'axis',
				backgroundColor: '#1e293b',
				borderColor: '#334155',
				textStyle: { color: '#f1f5f9' },
				formatter: (params: any) => {
					const p = params[0];
					return `${p.name}<br/>${p.value.toLocaleString()} ₸`;
				}
			}
		};

		chart.setOption(option);
		
		const resize = () => chart.resize();
		window.addEventListener('resize', resize);
		return () => window.removeEventListener('resize', resize);
	});
</script>

<div bind:this={chartEl} style="height: {height}px" class="w-full"></div>
