// Сравнение до 4 товаров, хранение в localStorage.
const KEY = 'skidki-compare';
const MAX = 4;

function load(): string[] {
	try {
		const raw = localStorage.getItem(KEY);
		const arr = raw ? (JSON.parse(raw) as string[]) : [];
		return Array.isArray(arr) ? arr.slice(0, MAX) : [];
	} catch { return []; }
}
function save(ids: string[]) {
	try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch {}
}

class CompareStore {
	ids = $state<string[]>([]);
	ready = $state(false);
	init() { this.ids = load(); this.ready = true; }
	has(id: string) { return this.ids.includes(id); }
	toggle(id: string) {
		const has = this.has(id);
		let next: string[];
		if (has) next = this.ids.filter((x) => x !== id);
		else {
			if (this.ids.length >= MAX) return;
			next = [...this.ids, id];
		}
		this.ids = next; save(next);
	}
	clear() { this.ids = []; save([]); }
	get count() { return this.ids.length; }
	get full() { return this.ids.length >= MAX; }
}

export const compare = new CompareStore();
export const cmpId = (shop: string, sku: string) => `${shop}:${sku}`;
