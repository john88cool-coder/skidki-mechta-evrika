import type { Deal, Product } from '../types';

export interface StorageLike {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
}

const SNAP_KEY = 'skidki-product-snapshots';
const MAX_SNAPSHOTS = 120;

function defaultStorage(): StorageLike | null {
	try {
		return typeof localStorage !== 'undefined' ? localStorage : null;
	} catch {
		return null;
	}
}

function readMap(storage: StorageLike | null = defaultStorage()): Record<string, Product> {
	if (!storage) return {};
	try {
		const raw = storage.getItem(SNAP_KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw);
		return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, Product>) : {};
	} catch {
		return {};
	}
}

function writeMap(map: Record<string, Product>, storage: StorageLike | null = defaultStorage()): void {
	if (!storage) return;
	try {
		const entries = Object.entries(map);
		const trimmed = entries.length > MAX_SNAPSHOTS ? Object.fromEntries(entries.slice(entries.length - MAX_SNAPSHOTS)) : map;
		storage.setItem(SNAP_KEY, JSON.stringify(trimmed));
	} catch {
		/* quota / private mode */
	}
}

export function rememberProduct(product: Product, storage: StorageLike | null = defaultStorage()): void {
	const id = `${product.shop}:${product.sku}`;
	const map = readMap(storage);
	delete map[id];
	map[id] = {
		shop: product.shop,
		sku: product.sku,
		title: product.title,
		price: product.price,
		old_price: product.old_price ?? null,
		url: product.url,
		brand: product.brand ?? null,
		category: product.category ?? null,
		group: product.group ?? null,
		in_stock: product.in_stock,
		image: product.image ?? null,
		first_seen: product.first_seen ?? null,
		rating: product.rating ?? null,
		reviews_count: product.reviews_count ?? null
	};
	writeMap(map, storage);
}

export function getSnapshot(id: string, storage: StorageLike | null = defaultStorage()): Product | null {
	return readMap(storage)[id] ?? null;
}

export function resolveDealsWithSnapshots(
	ids: Iterable<string>,
	activeDeals: Deal[],
	storage: StorageLike | null = defaultStorage()
): { deals: Deal[]; archivedIds: Set<string> } {
	const byId = new Map<string, Deal>();
	for (const d of activeDeals) {
		byId.set(`${d.product.shop}:${d.product.sku}`, d);
	}
	const snapMap = readMap(storage);
	let dirty = false;
	const deals: Deal[] = [];
	const archivedIds = new Set<string>();

	for (const id of ids) {
		const live = byId.get(id);
		if (live) {
			deals.push(live);
			snapMap[id] = live.product;
			dirty = true;
			continue;
		}
		const snap = snapMap[id];
		if (snap) {
			const pct =
				snap.old_price && snap.old_price > snap.price
					? Math.round((1 - snap.price / snap.old_price) * 1000) / 10
					: null;
			deals.push({
				product: snap,
				signal: 'deal',
				drop_pct: pct,
				badges: []
			});
			archivedIds.add(id);
		}
	}
	if (dirty) writeMap(snapMap, storage);
	return { deals, archivedIds };
}
