<script lang="ts">
	import type { EChartsOption } from 'echarts';
	import type { EChartsType } from 'echarts/core';
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
	let chart: EChartsType | undefined;

	type GradientCtor = typeof import('echarts/core').graphic.LinearGradient;
	type EChartsRuntime = {
		init: typeof import('echarts/core').init;
		LinearGradient: GradientCtor;
	};

	let runtimePromise: Promise<EChartsRuntime> | null = null;

	function loadECharts(): Promise<EChartsRuntime> {
		if (!runtimePromise) {
			runtimePromise = Promise.all([
				import('echarts/core'),
				import('echarts/charts'),
				import('echarts/components'),
				import('echarts/renderers')
			]).then(([core, charts, components, renderers]) => {
				core.use([
					charts.LineChart,
					components.GridComponent,
					components.TooltipComponent,
					components.LegendComponent,
					components.MarkLineComponent,
					renderers.CanvasRenderer
				]);
				return { init: core.init, LinearGradient: core.graphic.LinearGradient };
			});
		}
		return runtimePromise;
	}

	function buildOption(
		LinearGradient: GradientCtor,
		dark: boolean,
		points: PricePoint[],
		fmt?: (label: string) => string
	): EChartsOption {
		const labels = points.map((p) => (fmt ? fmt(p.date) : p.date));
		const prices = points.map((p) => p.price);
		const lowest = prices.length ? Math.min(...prices) : 0;
		const olds = points.map((p) => (p.old_price && p.old_price > p.price ? p.old_price : null));
		const hasOld = olds.some((v) => v !== null);
		const all = [...prices, ...(olds.filter((v) => v !== null) as number[])];
		const hi = all.length ? Math.max(...all) : 0;
		const lo = all.length ? Math.min(...all) : 0;
		const pad = Math.max((hi - lo) * 0.12, hi * 0.06, 1);
		const ink = dark ? '#93aaa1' : '#5a6b64';
		const gridLine = dark ? '#1e2e28' : '#ede9e3';
		const accent = dark ? '#ff6b4a' : '#ff3b1f';
		return {
			backgroundColor: 'transparent',
			grid: { top: hasOld ? 30 : 14, right: 16, bottom: 28, left: 56 },
			legend: hasOld
				? { top: 0, right: 0, itemWidth: 14, itemHeight: 2, textStyle: { color: ink, fontSize: 11 }, data: ['Цена', 'На ценнике'] }
				: undefined,
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
				min: Math.max(0, Math.floor((lo - pad) / 1000) * 1000),
				max: Math.ceil((hi + pad) / 1000) * 1000,
				axisLine: { show: false },
				splitLine: { lineStyle: { color: gridLine } },
				axisLabel: { color: ink, fontSize: 10, fontFamily: 'JetBrains Mono', formatter: (v: number) => `${Math.round(v / 1000)}k` }
			},
			series: [
				{
					name: 'Цена',
					type: 'line',
					data: prices,
					step: 'end',
					showSymbol: points.length <= 60,
					symbol: 'circle',
					symbolSize: 4,
					lineStyle: { color: accent, width: 2.2 },
					itemStyle: { color: accent, borderColor: dark ? '#0c1210' : '#fff', borderWidth: 1.5 },
					markLine: {
						silent: true,
						symbol: 'none',
						lineStyle: { color: dark ? '#3a5a4a' : '#b8c8bd', type: 'dashed', width: 1 },
						label: { color: ink, fontSize: 10, formatter: 'минимум', position: 'insideStartTop' },
						data: [{ yAxis: lowest }]
					},
					areaStyle: {
						color: new LinearGradient(0, 0, 0, 1, [
							{ offset: 0, color: dark ? 'rgba(255,91,54,0.18)' : 'rgba(255,59,31,0.12)' },
							{ offset: 1, color: 'rgba(255,59,31,0)' }
						])
					}
				},
				...(hasOld
					? [
							{
								name: 'На ценнике',
								type: 'line' as const,
								data: olds,
								step: 'end' as const,
								showSymbol: false,
								connectNulls: false,
								lineStyle: { color: ink, width: 1.4, type: 'dashed' as const, opacity: 0.8 },
								itemStyle: { color: ink }
							}
						]
					: [])
			],
			tooltip: {
				trigger: 'axis',
				backgroundColor: dark ? '#1a2e26' : '#fff',
				borderColor: dark ? '#2a3d34' : '#e8e2da',
				borderWidth: 1,
				padding: [8, 10],
				textStyle: { color: dark ? '#eef4f0' : '#0e1a15', fontSize: 12 },
				formatter: (params: unknown) => {
					const list = (Array.isArray(params) ? params : [params]) as Array<{ name?: string; seriesName?: string; value?: number | null }>;
					const rows = list
						.filter((p) => p.value != null)
						.map((p) => `${p.seriesName === 'На ценнике' ? 'на ценнике ' : ''}<b>${formatPrice(p.value as number)}</b>`);
					return `${list[0]?.name ?? ''}<br/>${rows.join('<br/>')}`;
				}
			}
		};
	}

	$effect(() => {
		const el = chartEl;
		const dark = theme.current === 'dark';
		const points = data;
		const fmt = labelFormatter;
		if (!el) return;
		let cancelled = false;
		void loadECharts().then((rt) => {
			if (cancelled || !el.isConnected) return;
			chart = chart ?? rt.init(el);
			chart.setOption(buildOption(rt.LinearGradient, dark, points, fmt), true);
		}).catch((error) => {
			// Чанк графика не догрузился: сбрасываем промис, чтобы следующий
			// прогон эффекта (смена темы/данных) повторил попытку.
			console.error('echarts load failed', error);
			runtimePromise = null;
		});
		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		const el = chartEl;
		if (!el) return;
		const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => chart?.resize()) : null;
		ro?.observe(el);
		const onResize = () => chart?.resize();
		window.addEventListener('resize', onResize);
		return () => {
			ro?.disconnect();
			window.removeEventListener('resize', onResize);
			chart?.dispose();
			chart = undefined;
		};
	});
</script>

<div bind:this={chartEl} style="height: {height}px" class="w-full"></div>
