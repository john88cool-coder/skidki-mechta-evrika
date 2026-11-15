import type { Deal } from '../types';
import { formatPrice } from './format.ts';

/**
 * Вердикт ИС о скидке — единственный ответ на вопрос «настоящая ли она».
 *
 * Раньше карточка показывала одновременно «Честная скидка», «Подозрительная
 * скидка», «по истории −28%» и «value 66» — противоречиво и без вывода.
 * Теперь из тех же полей экспорта выводится ровно одно из пяти состояний.
 *
 * - honest   — история подтверждает падение, и оно близко к заявленному;
 * - inflated — цена правда упала, но магазин завышает процент;
 * - pumped   — цену подняли перед скидкой; падение считаем от прежней цены;
 * - painted  — по истории цена не двигалась: скидка нарисована от старой цены;
 * - unknown  — истории меньше 3 дней, судить рано.
 */
export type VerdictKind = 'honest' | 'inflated' | 'pumped' | 'painted' | 'unknown';

export interface Verdict {
	kind: VerdictKind;
	/** Короткая подпись для чипа. */
	label: string;
	/** Одно предложение: что это значит для покупателя. */
	hint: string;
	/** Заявленная магазином скидка, %. */
	claimed: number | null;
	/** Подтверждённая историей скидка, % (0 — не двигалась, null — неизвестно). */
	real: number | null;
}

/** Поля среза, из которых выводится вердикт. */
export type VerdictInput = Pick<Deal, 'drop_pct' | 'fair_discount' | 'pump_price'>;

/** Разница, начиная с которой заявленный процент считаем завышенным (п.п.). */
export const INFLATION_GAP = 15;

export const VERDICT_ORDER: VerdictKind[] = ['honest', 'inflated', 'pumped', 'painted', 'unknown'];

export const VERDICT_LABELS: Record<VerdictKind, string> = {
	honest: 'Честная',
	inflated: 'Завышена',
	pumped: 'Накрутка',
	painted: 'Нарисована',
	unknown: 'Без истории'
};

/** Цена действительно ниже прежней: такие позиции попадают в «реально подешевело». */
export function isReal(kind: VerdictKind): boolean {
	return kind === 'honest' || kind === 'inflated' || kind === 'pumped';
}

export function verdictOf(deal: VerdictInput): Verdict {
	const claimed = deal.drop_pct ?? null;
	const real = deal.fair_discount ?? null;
	if (real === null) {
		return {
			kind: 'unknown', label: VERDICT_LABELS.unknown, claimed, real,
			hint: 'Истории меньше 3 дней — проверить скидку пока нечем.'
		};
	}
	if (real <= 0) {
		return {
			kind: 'painted', label: VERDICT_LABELS.painted, claimed, real: 0,
			hint: 'Цена не ниже обычной: «скидка» посчитана от завышенной старой цены.'
		};
	}
	if (deal.pump_price) {
		return {
			kind: 'pumped', label: VERDICT_LABELS.pumped, claimed, real,
			hint: `Перед скидкой цену поднимали до ${formatPrice(deal.pump_price)}. От прежней цены это −${Math.round(real)}%.`
		};
	}
	if (claimed !== null && claimed - real >= INFLATION_GAP) {
		return {
			kind: 'inflated', label: VERDICT_LABELS.inflated, claimed, real,
			hint: `Цена правда упала на ${Math.round(real)}%, но магазин пишет −${Math.round(claimed)}%.`
		};
	}
	return {
		kind: 'honest', label: VERDICT_LABELS.honest, claimed, real,
		hint: `История подтверждает: цена ниже обычной на ${Math.round(real)}%.`
	};
}

/**
 * Ключ сортировки «по реальной выгоде»: сначала подтверждённое падение,
 * затем то, что проверить нельзя, в конце — нарисованные.
 */
export function realRank(deal: VerdictInput): number {
	const v = verdictOf(deal);
	if (isReal(v.kind)) return 1000 + (v.real ?? 0);
	if (v.kind === 'unknown') return 500 + (v.claimed ?? 0) / 10;
	return v.claimed ? -(100 - v.claimed) : -100;
}

export function countVerdicts(deals: VerdictInput[]): Record<VerdictKind, number> {
	const out: Record<VerdictKind, number> = { honest: 0, inflated: 0, pumped: 0, painted: 0, unknown: 0 };
	for (const d of deals) out[verdictOf(d).kind] += 1;
	return out;
}
