# skidki-mechta-evrika

Бот следит за ценами в шести магазинах Казахстана и пишет в Telegram о новых
скидках магазина от −20% (цена от 20 000 ₸) и о падениях цены по собственной
истории.

- **mechta.kz** — все товары 6 разделов (~7 600), JSON API каталога через Playwright.
- **evrika.com** — ~150 листовых категорий тех же разделов, `__NEXT_DATA__` через Playwright.
- **shop.kz** — 38 разделов /offers/<slug>/ (Битрикс, SSR), карточки в `data-product` JSON.
- **sulpak.kz** — 50 категорий /f/<className>/, SSR + AJAX /Filter/LoadProducts.
- **technodom.kz** — 6 корней каталога через API katalog/api/v2 (сортировка по скидке),
  ~9 200 позиций.
- **alser.kz** — все категории из сайтмапа через POST mobapi-v3-get-catalog, ~900 позиций.

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

## Веб-панель

Статическая панель на GitHub Pages: топ-скидки, графики истории цен, статус
обходов по магазинам, фильтры (магазин, группа, глубина скидки, поиск).

- Адрес: `https://john88cool-coder.github.io/skidki-mechta-evrika/`
- Фронтенд — `web/` (SvelteKit + Tailwind + ECharts), сборка — workflow
  `dashboard`, данные — workflow `crawl` (папка `data/` на gh-pages)
- Срез для панели: `skidki export` (пишет `web/static/data/*.json`)
- Карточки показывают миниатюру товара: парсеры берут первый кадр из ответа
  магазина, где CDN умеет ресайз — просят уменьшенную версию (mechta `?w=400`:
  17 КБ вместо 115 КБ); картинки грузятся лениво и прямо с CDN магазинов,
  трафик панели их не кэширует

Локально:

```bash
cd web
npm install
python -m skidki.export   # данные из локальной базы в web/static/data
npm run dev
```

## Workflows

| Workflow | Когда | Что делает |
|---|---|---|
| crawl | каждые 2 часа (в :17) | обход 5 магазинов, Telegram, база → кэш Actions, данные → gh-pages |
| dashboard | push в `web/**` | сборка панели → gh-pages |
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
