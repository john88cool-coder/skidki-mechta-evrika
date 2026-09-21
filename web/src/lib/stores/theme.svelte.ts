type Theme = 'light' | 'dark';

class ThemeStore {
	current = $state<Theme>('light');

	init() {
		this.current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
	}

	toggle() {
		this.current = this.current === 'dark' ? 'light' : 'dark';
		document.documentElement.dataset.theme = this.current;
		try { localStorage.setItem('skidki-theme', this.current); } catch { /* Theme still works when storage is unavailable. */ }
	}
}

export const theme = new ThemeStore();
