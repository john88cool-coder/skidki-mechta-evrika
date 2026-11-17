/** Разделы панели: одни и те же в шапке и в нижней панели телефона. */
export type NavKey = 'home' | 'deals' | 'shops' | 'favorites';

export interface NavItem {
	key: NavKey;
	/** Путь без base: '/' или '/deals'. */
	path: string;
	label: string;
}

export const NAV_ITEMS: NavItem[] = [
	{ key: 'home', path: '/', label: 'Сегодня' },
	{ key: 'deals', path: '/deals', label: 'Каталог' },
	{ key: 'shops', path: '/shops', label: 'Магазины' },
	{ key: 'favorites', path: '/favorites', label: 'Избранное' }
];

/** Раздел активен на своей странице и на вложенных; главная — только на самой себе. */
export function isActive(pathname: string, path: string, base = ''): boolean {
	const clean = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
	if (path === '/') return clean === base || clean === `${base}/` || (base === '' && clean === '/');
	const href = `${base}${path}`;
	return clean === href || clean.startsWith(`${href}/`);
}
