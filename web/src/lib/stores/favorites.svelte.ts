// Избранное: локально в браузере, без бэкенда. Хватает для кейса "отследить товар".
const KEY = 'skidki-favorites';

function load(): Set<string> {
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return new Set();
		const arr = JSON.parse(raw) as string[];
		return new Set(Array.isArray(arr) ? arr : []);
	} catch {
		return new Set();
	}
}
function save(set: Set<string>) {
	try {
		localStorage.setItem(KEY, JSON.stringify([...set]));
	} catch { /* quota / private mode */ }
}

class FavoritesStore {
	ids = $state<Set<string>>(new Set());
	ready = $state(false);

	init() {
		this.ids = load();
		this.ready = true;
	}
	has(id: string) { return this.ids.has(id); }
	toggle(id: string) {
		const next = new Set(this.ids);
		if (next.has(id)) next.delete(id); else next.add(id);
		this.ids = next;
		save(next);
	}
	add(id: string) {
		if (this.ids.has(id)) return;
		const next = new Set(this.ids); next.add(id);
		this.ids = next; save(next);
	}
	remove(id: string) {
		if (!this.ids.has(id)) return;
		const next = new Set(this.ids); next.delete(id);
		this.ids = next; save(next);
	}
	clear() { this.ids = new Set(); save(this.ids); }
	get count() { return this.ids.size; }
	get list(): string[] { return [...this.ids]; }
}

export const favorites = new FavoritesStore();
export const favId = (shop: string, sku: string) => `${shop}:${sku}`;
