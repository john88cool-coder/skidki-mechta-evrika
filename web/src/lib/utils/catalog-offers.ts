import type { CatalogIndex, CatalogRow } from '../types';

/**
 * Строка каталога как кандидат в офферы. После задачи 6 экспорт пишет в
 * `exact_model` ключ той же комплектации (`string | null`); тип CatalogRow
 * пока объявляет поле литеральным null, поэтому офферы принимают его через
 * структурно совместимое расширение.
 */
export type OfferRow = Omit<CatalogRow, 'exact_model'> & { exact_model: string | null };

/** Состояние блока «в других магазинах»: собранные офферы и полнота данных. */
export interface OffersState {
	offers: OfferRow[];
	/** Загружены не все индексы магазинов — офферы неполные. */
	partial: boolean;
	/** Подпись неполноты: «среди загруженных предложений»; null — данные полные. */
	note: string | null;
}

/**
 * Собирает актуальные доступные предложения той же комплектации
 * (`exact_model` цели) из уже загруженных индексов catalog-v2.
 *
 * Возвращает null, когда у цели нет подтверждённого артикула: без него блок
 * скрыт — совпадение по названию не доказывает ту же модель. Identity цели
 * исключается всегда (дубликат в чужом индексе не считается оффером); для
 * каждого магазина остаётся самая низкая доступная цена, офферы сортируются
 * по цене, магазину и SKU.
 */
export function offersFor(
	target: { product: CatalogRow['product']; exact_model: string | null },
	indexes: Map<string, CatalogIndex>
): OfferRow[] | null {
	const exactModel = target.exact_model;
	if (!exactModel) return null; // одинаковые названия без артикула не сравниваем
	const targetIdentity = `${target.product.shop}:${target.product.sku}`;
	const bestPerShop = new Map<string, OfferRow>();
	for (const catalogIndex of indexes.values()) {
		for (const row of catalogIndex.rows) {
			if (row.exact_model !== exactModel) continue;
			const identity = `${row.product.shop}:${row.product.sku}`;
			if (identity === targetIdentity) continue; // сама цель — не оффер
			if (row.product.in_stock === false) continue; // только доступные
			if (row.product.price <= 0) continue;
			const prev = bestPerShop.get(row.product.shop);
			if (!prev || row.product.price < prev.product.price) bestPerShop.set(row.product.shop, row);
		}
	}
	return [...bestPerShop.values()].sort(
		(a, b) =>
			a.product.price - b.product.price ||
			(a.product.shop < b.product.shop ? -1 : a.product.shop > b.product.shop ? 1 : 0) ||
			(a.product.sku < b.product.sku ? -1 : a.product.sku > b.product.sku ? 1 : 0)
	);
}

/**
 * Офферы с оценкой полноты: индексы, чьи магазины объявлены в манифесте, но не
 * загружены, могли бы добавить предложения — тогда блок честно помечается
 * «среди загруженных предложений». Цель без ключа по-прежнему скрывает блок.
 */
export function partialOffers(
	target: { product: CatalogRow['product']; exact_model: string | null },
	indexes: Map<string, CatalogIndex>,
	knownShops: string[]
): OffersState | null {
	const offers = offersFor(target, indexes);
	if (offers === null) return null;
	const shopsInCatalog = new Set(
		[...indexes.values()].flatMap((catalogIndex) => catalogIndex.rows.map((row) => row.product.shop))
	);
	const missing = knownShops.filter((shop) => !shopsInCatalog.has(shop));
	const partial = missing.length > 0;
	return { offers, partial, note: partial ? 'среди загруженных предложений' : null };
}

/** Скрытые внутренние состояния блока: «ещё не запрашивали» и «товару ключа нет». */
export type OffersVisibilityInput = {
	/** Блок собран для этого товара (shop:sku); null — запрос ещё не завершался. */
	ownerIdentity: string | null;
	/** Итог запроса: результат сборки или null, если state не установлен (сбой). */
	state: { kind: 'hidden' | 'ready' | 'empty' } | null;
	/** Сбой загрузки — блок с ошибкой и «Повторить» виден и без state. */
	error: string | null;
};

/**
 * Видим ли блок офферов для товара. Ответ применяется только к запросившему
 * товару (запоздавший ответ A не рендерится на B), а сбой загрузки виден сам
 * по себе: без state — с сообщением об ошибке и кнопкой «Повторить».
 */
export function offersVisibleFor(
	cardIdentity: string | null | undefined,
	input: OffersVisibilityInput
): boolean {
	if (!cardIdentity || input.ownerIdentity !== cardIdentity) return false;
	if (input.error !== null) return true;
	return input.state !== null && input.state.kind !== 'hidden';
}
