# skidki-mechta-evrika

Бот следит за ценами в mechta.kz и evrika.com и пишет в Telegram о новых скидках
магазина от −20% (цена от 20 000 ₸) и о падениях цены по собственной истории.

- **mechta.kz** — все товары 6 разделов (~7 600), JSON API каталога через Playwright.
- **evrika.com** — ~150 листовых категорий тех же разделов, `__NEXT_DATA__` через Playwright.

Сигналы: новая скидка магазина от `deal_pct`% (первый обход молча запоминает
текущие) · цена ниже медианы за 14 дней на `drop_pct`% · минимум за 30 дней ·
цель из `rules.toml` · возврат в наличие позиции с целью. Одна сводка на обход — по группам, с кнопкой настройки групп.

## Запуск на домашнем ПК (Планировщик Windows)

mechta блокирует IP дата-центров GitHub (Cloudflare «Attention Required»), поэтому
обход идёт с домашнего ПК — оттуда проходят оба магазина.

1. Скопировать `.env.example` в `.env` и вписать `TELEGRAM_BOT_TOKEN`.
2. `pip install -e ".[dev]"` и `python -m playwright install chromium`.
3. `powershell -ExecutionPolicy Bypass -File deploy\install_task.ps1` — задача
   `skidki-crawl`: каждые 2 часа (в :17), пока вы в системе; пропущенный запуск
   выполняется при первой возможности.

Логи — `logs\crawl-ДАТА.log` (14 дней), база — `data\skidki.sqlite3`.
Удалить задачу: `Unregister-ScheduledTask -TaskName skidki-crawl -Confirm:$false`.

Пороги и цели — в [`rules.toml`](rules.toml), код не нужен.

### Сводка и группы уведомлений

Одна сводка на обход: находки по шести группам (разделы mechta; категории evrika
разложены по ним же), у каждой — процент, цена, старая цена и ссылка на товар.
Кнопка «⚙️ Группы уведомлений» под сводкой и команда `/groups` включают и выключают
группы; `/status` — когда были обходы и сколько находок в очереди.

Кнопки обслуживает слушатель — отдельная задача Планировщика:
`powershell -ExecutionPolicy Bypass -File deploy\install_bot_task.ps1` (`skidki-bot`:
при входе в Windows, перезапуск после сбоя, лог — `logs\bot.log`).

## Workflows

| Workflow | Когда | Что делает |
|---|---|---|
| crawl | вручную (расписание снято: mechta режет IP GitHub) | обход, оценка, Telegram, база → кэш Actions |
| watchdog | вручную | тревога, если обходов нет дольше 6 часов |
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
