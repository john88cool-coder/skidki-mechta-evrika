export function formatPrice(price: number): string {
	return price.toLocaleString('ru-RU').replace(/,/g, ' ') + ' ₸';
}

export function formatPct(pct: number): string {
	return `−${Math.round(pct)}%`;
}

export function formatDate(dateStr: string): string {
	const date = new Date(dateStr);
	return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

export function formatTime(dateStr: string): string {
	const date = new Date(dateStr);
	return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

export function timeAgo(dateStr: string): string {
	const date = new Date(dateStr);
	const now = new Date();
	const diff = Math.floor((now.getTime() - date.getTime()) / 1000);

	if (diff < 60) return 'только что';
	if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
	if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
	return `${Math.floor(diff / 86400)} дн назад`;
}

const SHOP_LABELS: Record<string, string> = {
	mechta: 'Мечта',
	evrika: 'Эврика',
	shopkz: 'Shop.kz',
	sulpak: 'Сулпак',
	technodom: 'Технодом',
	alser: 'Алсер',
	kaspi: 'Kaspi',
	wb: 'Wildberries',
	ozon: 'Ozon',
	satu: 'Satu.kz',
	dns: 'DNS'
};
export function shopLabel(shop: string): string {
	return SHOP_LABELS[shop] ?? shop;
}

export function groupLabel(group: string): string {
	const labels: Record<string, string> = {
		phones: '📱 Смартфоны',
		computers: '💻 Ноутбуки',
		tv: '📺 ТВ',
		home: '🏠 Для дома',
		kitchen: '🍳 Кухня',
		beauty: '💄 Красота'
	};
	return labels[group] ?? group;
}

export function badgeLabel(badge: string): string {
	const m: Record<string, string> = {
		'Выбор ИС': 'Выбор ИС',
		'Честная скидка': 'Честная',
		'Топ-Бренд': 'Топ-Бренд',
		'Рисованная?': 'Рисованная?'
	};
	return m[badge] ?? badge;
}

export function badgeTone(badge: string): 'pick' | 'fair' | 'brand' | 'warn' {
	if (badge === 'Выбор ИС') return 'pick';
	if (badge === 'Честная скидка') return 'fair';
	if (badge === 'Топ-Бренд') return 'brand';
	return 'warn';
}
