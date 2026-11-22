<script lang="ts">
	import { base } from '$app/paths';
	import { formatPrice } from '$lib/utils/format';
	import { VERDICT_LABELS, INFLATION_GAP } from '$lib/utils/verdict';
	import {
		LOW_WINDOW_DAYS,
		MIN_HISTORY_DAYS,
		PUMP_GAP,
		RETENTION_DAYS,
		TREND_WINDOW_DAYS,
		ruDays
	} from '$lib/utils/quality';
	import { ArrowLeft } from '@lucide/svelte';

	/**
	 * Пример воспроизводит тест накрутки (tests/test_pump_baseline.py):
	 * 16 дней по 300 000 → 9 дней по 525 000 → 3 дня по 200 000, зачёркнутая
	 * цена 599 990. Проценты считаются здесь же из этих цен — не готовые числа.
	 */
	const example = {
		former: 300_000,
		pumped: 525_000,
		sale: 200_000,
		paintedOld: 599_990,
		daysFormer: 16,
		daysPumped: 9,
		daysSale: 3
	};
	const claimedPct = Math.round((1 - example.sale / example.paintedOld) * 100);
	const realPct = Math.round((1 - example.sale / example.former) * 100);
	const pumpGapPct = Math.round(PUMP_GAP * 100);
</script>

<svelte:head><title>Как мы считаем — skidki</title></svelte:head>

<a href="{base}/shops" class="inline-flex items-center gap-1.5 text-sm font-medium mb-5" style="color:var(--ink-3)">
	<ArrowLeft size={14} /> К магазинам
</a>

<div class="mb-6">
	<p class="page-eyebrow">Методика</p>
	<h1 class="page-heading">Как мы <em>считаем</em></h1>
	<p class="page-description">
		Вердикт о скидке — единственный ответ на вопрос «настоящая ли она». Ниже — реальный расчёт:
		те же пороги, что используют сигналы и чипы интерфейса.
	</p>
</div>

<div class="grid gap-4">
	<section class="m-card">
		<h2>Реальный расчёт за {ruDays(TREND_WINDOW_DAYS)}</h2>
		<p>
			«Обычная цена» — это медиана цены за {ruDays(TREND_WINDOW_DAYS)}, взвешенная по времени:
			цена, державшаяся неделю, весит больше, чем распродажа на два часа. Снижение считается
			от этой медианы, а не от зачёркнутой цены магазина. Подтверждённое падение — честное,
			заявленный процент сильно выше подтверждённого (на {INFLATION_GAP}+ п.п.) — {VERDICT_LABELS.inflated.toLowerCase()}.
		</p>
	</section>

	<section class="m-card">
		<h2>Прежний уровень вместо накрутки</h2>
		<p>
			Магазины поднимают цену перед «скидкой». Если медиана за {ruDays(LOW_WINDOW_DAYS)} ниже
			медианы окна тренда хотя бы на {pumpGapPct}%, базой сравнения становится прежний уровень,
			а вердикт — «{VERDICT_LABELS.pumped}»: падение считается от прежней цены, и в подсказке видна
			цена, до которой товар поднимали.
		</p>
		<div class="m-example">
			<p class="m-example-title">Пример: как одна цена получает два процента</p>
			<p class="m-line">
				{ruDays(example.daysFormer)} по {formatPrice(example.former)}
				→ {ruDays(example.daysPumped)} по {formatPrice(example.pumped)}
				→ {ruDays(example.daysSale)} по {formatPrice(example.sale)}
			</p>
			<p class="m-line">
				Магазин пишет <del>{formatPrice(example.paintedOld)}</del>
				<strong>−{claimedPct}%</strong> — но это процент от нарисованной цены.
			</p>
			<p class="m-line">
				Медиана за {ruDays(TREND_WINDOW_DAYS)} — {formatPrice(example.pumped)}: именно до неё подняли цену.
			</p>
			<p class="m-line">
				Медиана за {ruDays(LOW_WINDOW_DAYS)} — {formatPrice(example.former)}: прежний уровень.
			</p>
			<p class="m-line">
				От прежнего уровня снижение всего <strong>−{realPct}%</strong> → вердикт «{VERDICT_LABELS.pumped}».
			</p>
		</div>
	</section>

	<section class="m-card">
		<h2>Минимальное покрытие отрезков</h2>
		<p>
			История хранится отрезками между обходами. Вердикт появляется только когда позиция
			наблюдается {ruDays(MIN_HISTORY_DAYS)} и дольше: медиана из пары наблюдений — не база
			сравнения. Покрытие считается по отрезкам, а не по числу точек на графике; графики
			и история хранятся {ruDays(RETENTION_DAYS)}.
		</p>
	</section>

	<section class="m-card">
		<h2>{VERDICT_LABELS.unknown} — это не оценка магазина</h2>
		<p>
			«{VERDICT_LABELS.unknown}» значит лишь одно: историй меньше {ruDays(MIN_HISTORY_DAYS)}, судить
			рано — ни «хорошо», ни «плохо». Ноль оценок покупателей и пустая история — тоже
			диагностический показатель, а не вывод о качестве магазина. Скидка без подтверждения
			не попадает в «реально подешевело», пока история не накопится.
		</p>
	</section>

	<section class="m-card">
		<h2>Ограничение сопоставления</h2>
		<p>
			«Та же комплектация в других магазинах» сопоставляется только по подтверждённому артикулу
			производителя: без него сопоставления нет. Доли магазинов на «Магазинах» считаются по всему
			каталогу v2 и не сравниваются с выборкой витрины: у витрины другая выборка, поэтому
			на несопоставимых выборках порядковое место не показывается.
		</p>
	</section>

	<section class="m-card">
		<h2>Пять вердиктов</h2>
		<ul class="m-verdicts">
			<li><b>{VERDICT_LABELS.honest}</b> — история подтверждает падение, и оно близко к заявленному.</li>
			<li><b>{VERDICT_LABELS.inflated}</b> — цена правда упала, но заявленный процент выше подтверждённого на {INFLATION_GAP}+ п.п.</li>
			<li><b>{VERDICT_LABELS.pumped}</b> — цену подняли перед скидкой; падение считаем от прежнего уровня.</li>
			<li><b>{VERDICT_LABELS.painted}</b> — по истории цена не двигалась: скидка нарисована от старой цены.</li>
			<li><b>{VERDICT_LABELS.unknown}</b> — историй меньше {ruDays(MIN_HISTORY_DAYS)}, судить рано.</li>
		</ul>
	</section>
</div>

<style>
	.m-card {
		border-radius: var(--radius);
		padding: 18px 20px;
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.m-card h2 {
		font-size: 16px;
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--ink);
	}
	.m-card p {
		margin-top: 8px;
		font-size: 14px;
		line-height: 1.55;
		color: var(--ink-2);
	}
	.m-example {
		margin-top: 12px;
		border-radius: 12px;
		padding: 12px 14px;
		background: var(--paper-2);
		border: 1px solid var(--line);
	}
	.m-example-title {
		margin-top: 0 !important;
		font-size: 12px !important;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-4) !important;
	}
	.m-line {
		margin-top: 6px !important;
		font-family: var(--font-mono);
		font-size: 13px !important;
		color: var(--ink) !important;
	}
	.m-line strong {
		color: var(--success);
	}
	.m-verdicts {
		margin-top: 8px;
		display: grid;
		gap: 6px;
		font-size: 14px;
		line-height: 1.5;
		color: var(--ink-2);
		list-style: none;
		padding: 0;
	}
	.m-verdicts b {
		color: var(--ink);
	}
</style>
