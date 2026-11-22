import { base } from '$app/paths';
import { createCatalogLoader, type CatalogLoader } from '$lib/utils/catalog-source';

/**
 * Хранилище catalog-v2: чистый лоадер (кэш по стороне+магазину+хешу, общие
 * in-flight промисы, revalidation маленьких файлов) с приложечным инстансом.
 * Реактивное состояние не требуется — карточки ждут промисы loadIndex/loadHistory.
 */
export const catalog: CatalogLoader = createCatalogLoader((input, init) => fetch(input, init), base);
