import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	EMPTY_QUALITY_TEXT,
	LOW_WINDOW_DAYS,
	MIN_HISTORY_DAYS,
	PUMP_GAP,
	RETENTION_DAYS,
	TREND_WINDOW_DAYS,
	qualitySummary,
	ruDays,
	type CatalogQuality
} from '../src/lib/utils/quality.ts';
import { MIN_COVERAGE_DAYS } from '../src/lib/utils/history.ts';
import { INFLATION_GAP } from '../src/lib/utils/verdict.ts';

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(webRoot, '..');

const quality = (over: Partial<CatalogQuality>): CatalogQuality => ({
	catalog_rows: 5,
	available_rows: 5,
	available_with_baseline: 5,
	available_with_rating: 5,
	advertised_rows: 5,
	advertised_checked: 0,
	advertised_painted: 0,
	...over
});

/* ===== Три состояния подписи «проверено X из Y» ===== */

test('0/0 — пустая выборка: «нет проверенных скидок»', () => {
	const s = qualitySummary(
		quality({
			catalog_rows: 0,
			available_rows: 0,
			available_with_baseline: 0,
			available_with_rating: 0,
			advertised_rows: 0
		}),
		null
	);
	assert.equal(s.state, 'empty');
	assert.equal(s.text, EMPTY_QUALITY_TEXT);
	assert.equal(s.paintedShare, null);
});

test('0/0 — каталог есть, заявленных скидок ни одной: то же «нет проверенных скидок»', () => {
	const s = qualitySummary(quality({ advertised_rows: 0 }), null);
	assert.equal(s.state, 'empty');
	assert.equal(s.text, EMPTY_QUALITY_TEXT);
});

test('0 из 5 — заявленные скидки есть, проверить нечем', () => {
	const s = qualitySummary(quality({ advertised_checked: 0, advertised_painted: 0 }), null);
	assert.equal(s.state, 'none-checked');
	assert.equal(s.text, '0 из 5');
	assert.equal(s.paintedShare, null);
});

test('3 из 5 — проверенные считаются по всему каталогу, нарисованные — внутри проверенных', () => {
	const s = qualitySummary(quality({ advertised_checked: 3, advertised_painted: 1 }), null);
	assert.equal(s.state, 'checked');
	assert.equal(s.text, '3 из 5');
	assert.equal(s.checked, 3);
	assert.equal(s.painted, 1);
	assert.ok(Math.abs(s.paintedShare! - 1 / 3) < 1e-9);
	assert.equal(s.sample, 'по всему каталогу');
});

test('магазин без каталога v2 — подписан размер выборки витрины', () => {
	const s = qualitySummary(null, { claimed: 7, checked: 5, painted: 2 });
	assert.equal(s.state, 'showcase');
	assert.equal(s.text, '5 из 7');
	assert.equal(s.sample, 'по витрине');
	assert.ok(Math.abs(s.paintedShare! - 2 / 5) < 1e-9);
	assert.equal(qualitySummary(null, { claimed: 0, checked: 0, painted: 0 }).text, EMPTY_QUALITY_TEXT);
});

/* ===== Подписи окон методики — из констант кода ===== */

test('подписи окон строятся из констант, а не параллельных чисел', () => {
	assert.equal(ruDays(TREND_WINDOW_DAYS), '14 дней');
	assert.equal(ruDays(LOW_WINDOW_DAYS), '30 дней');
	assert.equal(ruDays(RETENTION_DAYS), '35 дней');
	assert.equal(ruDays(MIN_HISTORY_DAYS), '3 дня');
});

test('порог методики совпадает с порогом карточки и вердикта', () => {
	// verdictOf: «Истории меньше 3 дней» ↔ priceViewOf: «Пока мало истории».
	assert.equal(MIN_HISTORY_DAYS, MIN_COVERAGE_DAYS);
	// «Завышена» — тот же зазор, что в verdictOf.
	assert.equal(INFLATION_GAP, 15);
});

/* ===== Константы окон отвечают Thresholds бэкенда ===== */

/** CI веба ставит только node — без python кросс-проверка не падает, а пропускается. */
function uvAvailable(): boolean {
	try {
		execFileSync('uv', ['--version'], { cwd: repoRoot, stdio: 'ignore', timeout: 30_000 });
		return true;
	} catch {
		return false;
	}
}

test('константы окон равны живым Thresholds бэкенда', { skip: !uvAvailable() }, () => {
	const script = [
		'import json',
		'from skidki.config import Thresholds',
		'from skidki.evaluate import PUMP_GAP',
		't = Thresholds()',
		'print(json.dumps({',
		"  'trend_window_days': t.trend_window_days,",
		"  'low_window_days': t.low_window_days,",
		"  'retention_days': t.retention_days,",
		"  'min_history_days': t.min_history_days,",
		"  'pump_gap': PUMP_GAP,",
		'}))'
	].join('\n');
	const out = execFileSync('uv', ['run', 'python', '-c', script], {
		cwd: repoRoot,
		encoding: 'utf8',
		timeout: 120_000
	});
	const th = JSON.parse(out);
	assert.equal(TREND_WINDOW_DAYS, th.trend_window_days);
	assert.equal(LOW_WINDOW_DAYS, th.low_window_days);
	assert.equal(RETENTION_DAYS, th.retention_days);
	assert.equal(MIN_HISTORY_DAYS, th.min_history_days);
	assert.equal(PUMP_GAP, th.pump_gap);
});
