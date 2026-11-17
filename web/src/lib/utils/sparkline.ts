import type { PricePoint } from '../types';

export type SparkTrend = 'down' | 'up' | 'flat';

export interface SparkPath {
	/** Ступенчатая линия цены: цена держится до следующего замера. */
	line: string;
	/** Та же линия, замкнутая на нижний край, — заливка под графиком. */
	area: string;
	/** Последняя цена ниже первой больше чем на 1% — down, выше — up. */
	trend: SparkTrend;
	/** Сколько дней с замерами попало в график. */
	days: number;
}

const round = (v: number) => Math.round(v * 10) / 10;

/** Одна цена на дату — последняя за день: в истории бывает по несколько замеров в сутки. */
export function dailyPrices(points: PricePoint[]): number[] {
	const byDate = new Map<string, number>();
	for (const point of points) {
		if (!Number.isFinite(point.price) || point.price <= 0) continue;
		byDate.set(point.date.slice(0, 10), point.price);
	}
	return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, price]) => price);
}

/** Мини-график цены для карточки. Меньше двух дней наблюдений — null: рисовать нечего. */
export function sparkline(points: PricePoint[], width = 240, height = 40, pad = 3): SparkPath | null {
	const prices = dailyPrices(points);
	if (prices.length < 2) return null;
	const min = Math.min(...prices);
	const max = Math.max(...prices);
	const step = (width - pad * 2) / (prices.length - 1);
	const y = (price: number) =>
		max === min ? height / 2 : round(pad + ((max - price) / (max - min)) * (height - pad * 2));
	let line = `M${round(pad)} ${y(prices[0])}`;
	for (let i = 1; i < prices.length; i += 1) {
		line += ` H${round(pad + step * i)} V${y(prices[i])}`;
	}
	const area = `${line} V${height} H${round(pad)} Z`;
	const first = prices[0];
	const last = prices[prices.length - 1];
	const trend: SparkTrend = last < first * 0.99 ? 'down' : last > first * 1.01 ? 'up' : 'flat';
	return { line, area, trend, days: prices.length };
}
