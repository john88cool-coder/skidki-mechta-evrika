/**
 * Качество покрытия данных магазина (задача 7).
 *
 * `CatalogQuality` — счётчики из manifest.json catalog-v2
 * (catalog_export.export_catalog): числитель и знаменатель каждой пары
 * относятся к одному набору строк — available_* считаются по доступным
 * позициям, advertised_* по позициям с заявленной скидкой магазина;
 * checked/painted — тот же критерий вердикта, что verdictOf в интерфейсе.
 *
 * Окна методики — те же пороги, что в бэкенде (skidki.config.Thresholds,
 * evaluate.PUMP_GAP): согласие проверяет тест, вызывающий живой python.
 */

export interface CatalogQuality {
	/** Все строки каталога магазина (v2). */
	catalog_rows: number;
	/** Строки в наличии. */
	available_rows: number;
	/** Доступные строки с известной обычной ценой (base_price). */
	available_with_baseline: number;
	/** Доступные строки с оценкой покупателей. */
	available_with_rating: number;
	/** Строки с заявленной скидкой — знаменатель «проверено X из Y». */
	advertised_rows: number;
	/** Заявленные скидки, проверенные историей (вердикт ≠ unknown). */
	advertised_checked: number;
	/** Из проверенных — нарисованные (вердикт painted, как в verdictOf). */
	advertised_painted: number;
}

export type QualityState = 'showcase' | 'empty' | 'none-checked' | 'checked';

export interface QualitySummary {
	state: QualityState;
	/** Главная строка: «3 из 5» или «нет проверенных скидок». */
	text: string;
	/** Откуда выборка: «по всему каталогу» или «по витрине». */
	sample: string;
	/** Проверено и нарисовано — для подписи и сортировки «честные выше». */
	checked: number;
	painted: number;
	/** Доля нарисованных среди проверенных; null — проверять нечего. */
	paintedShare: number | null;
}

/** Пустая выборка: проверять нечего — это не оценка магазина. */
export const EMPTY_QUALITY_TEXT = 'нет проверенных скидок';

/**
 * Подпись качества для /shops. Три состояния каталога v2: 0/0 — пустая
 * выборка («нет проверенных скидок»), «0 из 5» — заявленные скидки есть,
 * а истории не хватает, «3 из 5» — проверено три из пяти заявленных.
 * Для магазина без catalog-v2 подписывается размер выборки витрины.
 */
export function qualitySummary(
	quality: CatalogQuality | null,
	showcase: { claimed: number; checked: number; painted: number } | null
): QualitySummary {
	if (!quality) {
		const claimed = showcase?.claimed ?? 0;
		const checked = showcase?.checked ?? 0;
		const painted = showcase?.painted ?? 0;
		if (!claimed) {
			return { state: 'empty', text: EMPTY_QUALITY_TEXT, sample: 'по витрине', checked: 0, painted: 0, paintedShare: null };
		}
		return {
			state: 'showcase',
			text: `${checked} из ${claimed}`,
			sample: 'по витрине',
			checked,
			painted,
			paintedShare: checked ? painted / checked : null
		};
	}
	if (!quality.advertised_rows) {
		return { state: 'empty', text: EMPTY_QUALITY_TEXT, sample: 'по всему каталогу', checked: 0, painted: 0, paintedShare: null };
	}
	const checked = quality.advertised_checked;
	const painted = quality.advertised_painted;
	return {
		state: checked ? 'checked' : 'none-checked',
		text: `${checked} из ${quality.advertised_rows}`,
		sample: 'по всему каталогу',
		checked,
		painted,
		paintedShare: checked ? painted / checked : null
	};
}

/* ===== Окна методики: источники — Thresholds, honest_baseline, verdictOf ===== */

/** Окно тренда: медиана «обычной цены» (Thresholds.trend_window_days). */
export const TREND_WINDOW_DAYS = 14;
/** Длинное окно, ловящее подъём цены перед скидкой (Thresholds.low_window_days). */
export const LOW_WINDOW_DAYS = 30;
/** Хранение истории и глубина графика (Thresholds.retention_days). */
export const RETENTION_DAYS = 35;
/** Минимальное покрытие отрезков для вердикта (Thresholds.min_history_days). */
export const MIN_HISTORY_DAYS = 3;
/** Медиана длинного окна ниже окна тренда на эту долю — накрутка (evaluate.PUMP_GAP). */
export const PUMP_GAP = 0.1;

/** «14 дней», «3 дня» — подпись окна с русской плюрализацией. */
export function ruDays(n: number): string {
	const mod10 = n % 10;
	const mod100 = n % 100;
	let word = 'дней';
	if (mod10 === 1 && mod100 !== 11) word = 'день';
	else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) word = 'дня';
	return `${n} ${word}`;
}
