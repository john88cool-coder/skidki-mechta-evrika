# skidki-mechta-evrika

Бот следит за ценами в mechta.kz и evrika.com и пишет в Telegram о новых скидках
магазина от −20% (цена от 20 000 ₸) и о падениях цены по собственной истории.

- **mechta.kz** — все товары 6 разделов (~7 600), JSON API каталога через Playwright.
- **evrika.com** — ~150 листовых категорий тех же разделов, `__NEXT_DATA__` через Playwright.

Сигналы: новая скидка магазина от `deal_pct`% (первый обход молча запоминает
текущие) · цена ниже медианы за 14 дней на `drop_pct`% · минимум за 30 дней ·
цель из `rules.toml` · возврат в наличие позиции с целью. Одно сообщение на обход, не длиннее 10 строк.

## Настройка

1. Settings → Secrets and variables → Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. Пороги и цели — в [`rules.toml`](rules.toml) (правка + push, код не нужен).

## Workflows

| Workflow | Когда | Что делает |
|---|---|---|
| crawl | каждые 2 часа | обход, оценка, Telegram, база → кэш Actions |
| watchdog | 06:00 и 18:00 UTC | тревога, если обходов нет дольше 6 часов |
| tests | push в main | pytest на фикстурах |
| sample | вручную | пример карточек уведомлений на текущих скидках из базы |
| probe | вручную | проверка, пускает ли Cloudflare IP раннера |

База — SQLite в кэше Actions (каждый обход берёт свежую копию и сохраняет новую;
резервная копия — артефакт запуска на 7 дней). История хранится отрезками
«цена держалась с … по …», 35 дней.

## Локально

```bash
pip install -e ".[dev]"
python -m playwright install chromium
pytest -q
skidki crawl --console --shop mechta
```

Разведка сайтов и решения — [RECON_2026-09-13.md](RECON_2026-09-13.md).
