/**
 * Личная цель по товару из карточки: payload `w2_…` и ссылка боту владельца.
 *
 * Формат общий с ботом (`src/skidki/item_watch.py`):
 * `w2_<base64url(UTF8(JSON.stringify([shop, sku, maxPrice])))>` без padding.
 * В payload входят только публичные данные — магазин, точный SKU и целевая
 * цена; ни title, ни chat ID, ни токен бота в ссылку не попадают.
 * Ссылка строится только на `https://t.me/<username>?start=<payload>` и только
 * когда payload помещается в лимит параметра /start (64 символа); длинный SKU
 * уходит «Скопировать команду» `/watchitem <payload>` в лимите сообщения.
 */

export const WATCH_SHOPS = ['mechta', 'evrika', 'shopkz', 'sulpak', 'technodom', 'alser'] as const;
export type WatchShop = (typeof WATCH_SHOPS)[number];
export const PRICE_MIN = 1;
export const PRICE_MAX = 999_999_999;
export const PAYLOAD_PREFIX = 'w2_';
/** Лимит параметра deep-link `/start` в Telegram. */
export const START_LIMIT = 64;
/** Лимит текста сообщения Telegram. */
export const MESSAGE_LIMIT = 4096;
export const WATCH_COMMAND = '/watchitem';
/** Ключ настройки владельца в этом браузере (localStorage). */
export const OWNER_SETTING_KEY = 'skidki:owner-bot';

/** Тело payload — строго base64url-алфавит, padding запрещён. */
const PAYLOAD_BODY_RE = /^[A-Za-z0-9_-]+$/;
const PRICE_RE = /^\d+$/;
/** Username бота: 5–32, буквы/цифры/подчёркивание, начинается не с цифры, суффикс bot. */
const USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]*[bB][oO][tT]$/;

export interface WatchTarget {
	shop: string;
	sku: string;
	maxPrice: number;
}

/** Явная настройка владельца в этом браузере: публичный username его бота. */
export interface OwnerBotSetting {
	username: string;
	enabled: boolean;
}

function b64urlEncode(bytes: Uint8Array): string {
	let bin = '';
	for (const b of bytes) bin += String.fromCharCode(b);
	return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64urlDecode(text: string): Uint8Array | null {
	let b64 = text.replace(/-/g, '+').replace(/_/g, '/');
	while (b64.length % 4) b64 += '=';
	try {
		const bin = atob(b64);
		const out = new Uint8Array(bin.length);
		for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
		return out;
	} catch {
		return null;
	}
}

function isKnownShop(shop: string): boolean {
	return (WATCH_SHOPS as readonly string[]).includes(shop);
}

function validTarget(shop: string, sku: string, maxPrice: number): boolean {
	return (
		isKnownShop(shop) &&
		typeof sku === 'string' &&
		sku.trim().length > 0 &&
		Number.isSafeInteger(maxPrice) &&
		maxPrice >= PRICE_MIN &&
		maxPrice <= PRICE_MAX
	);
}

/**
 * Строит payload цели; null — данные не проходят валидацию или команда
 * `/watchitem <payload>` не помещается в лимит сообщения Telegram.
 */
export function encodeWatchPayload(shop: string, sku: string, maxPrice: number): string | null {
	if (!validTarget(shop, sku, maxPrice)) return null;
	const json = JSON.stringify([shop, sku, maxPrice]);
	const payload = PAYLOAD_PREFIX + b64urlEncode(new TextEncoder().encode(json));
	if (WATCH_COMMAND.length + 1 + payload.length > MESSAGE_LIMIT) return null;
	return payload;
}

/** Разбирает payload с полной валидацией; null — повреждён или подделан. */
export function decodeWatchPayload(payload: string): WatchTarget | null {
	if (typeof payload !== 'string' || !payload.startsWith(PAYLOAD_PREFIX)) return null;
	const body = payload.slice(PAYLOAD_PREFIX.length);
	if (!PAYLOAD_BODY_RE.test(body)) return null;
	const bytes = b64urlDecode(body);
	if (!bytes) return null;
	let text: string;
	try {
		text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
	} catch {
		return null;
	}
	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch {
		return null;
	}
	if (!Array.isArray(parsed) || parsed.length !== 3) return null;
	const [shop, sku, maxPrice] = parsed as unknown[];
	if (typeof shop !== 'string' || !isKnownShop(shop)) return null;
	if (typeof sku !== 'string' || sku.trim().length === 0) return null;
	if (
		typeof maxPrice !== 'number' ||
		!Number.isSafeInteger(maxPrice) ||
		maxPrice < PRICE_MIN ||
		maxPrice > PRICE_MAX
	) {
		return null;
	}
	return { shop, sku, maxPrice };
}

/** Цель вводится целым числом ₸ от 1 до 999999999, без разделителей разрядов. */
export function parseTargetPrice(raw: string): number | null {
	const text = raw.trim();
	if (!PRICE_RE.test(text)) return null;
	const value = Number(text);
	if (!Number.isSafeInteger(value) || value < PRICE_MIN || value > PRICE_MAX) return null;
	return value;
}

export function validBotUsername(username: string): boolean {
	return username.length >= 5 && username.length <= 32 && USERNAME_RE.test(username);
}

/** Ссылка боту: только `https://t.me/`, payload помещается в лимит /start. */
export function watchStartLink(username: string, payload: string): string | null {
	if (!validBotUsername(username)) return null;
	if (
		!payload.startsWith(PAYLOAD_PREFIX) ||
		!PAYLOAD_BODY_RE.test(payload.slice(PAYLOAD_PREFIX.length)) ||
		payload.length > START_LIMIT
	) {
		return null;
	}
	return `https://t.me/${username}?start=${payload}`;
}

/** Команда для длинного SKU: тот же payload, лимит проверяется в encode. */
export function watchCopyCommand(payload: string): string {
	return `${WATCH_COMMAND} ${payload}`;
}

export function watchShopAllowed(shop: string): boolean {
	return isKnownShop(shop);
}

const DEFAULT_SETTING: OwnerBotSetting = { username: '', enabled: false };

/** Читает настройку владельца; нет данных или мусор — выключено по умолчанию. */
export function loadOwnerSetting(storage: { getItem(key: string): string | null } | null): OwnerBotSetting {
	if (!storage) return { ...DEFAULT_SETTING };
	try {
		const raw = storage.getItem(OWNER_SETTING_KEY);
		if (!raw) return { ...DEFAULT_SETTING };
		const parsed: unknown = JSON.parse(raw);
		if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ...DEFAULT_SETTING };
		const { username, enabled } = parsed as Record<string, unknown>;
		if (typeof username !== 'string' || typeof enabled !== 'boolean') return { ...DEFAULT_SETTING };
		return { username, enabled };
	} catch {
		return { ...DEFAULT_SETTING };
	}
}

export function saveOwnerSetting(
	storage: { setItem(key: string, value: string): void } | null,
	setting: OwnerBotSetting
): void {
	if (!storage) return;
	try {
		storage.setItem(OWNER_SETTING_KEY, JSON.stringify(setting));
	} catch {
		// приватный режим браузера: настройка просто не сохранится
	}
}

/** CTA готов: владелец явно включил настройку с валидным username бота. */
export function ownerWatchReady(setting: OwnerBotSetting): boolean {
	return setting.enabled && validBotUsername(setting.username);
}

/** localStorage без сбоев: SSR и приватный режим дают null. */
export function safeStorage(): { getItem(key: string): string | null; setItem(key: string, value: string): void } | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		return localStorage;
	} catch {
		return null;
	}
}
