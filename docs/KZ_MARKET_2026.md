# Карта рынка электроники Казахстана — 2026

> Анализ для ИС `skidki` · 2026-09-22 · live-пробы HTTP + HTML/API
> Цель — какие магазины имеют смысл мониторить, их доступность для парсинга и приоритет интеграции.

## Топология

### T1 — критично покрыть (ядро ИС)

| Магазин | Домен | Масштаб | Категория | Стартовая доступность | Статус в ИС |
|---------|-------|---------|-----------|-----------------------|-------------|
| **Kaspi Магазин** | kaspi.kz/shop | №1 в KZ, ~70% GMV e-com, 13M MAU | маркетплейс, электроника — топ-3 | HTML 200, нет открытого JSON API, SSR + JS-гидрат | **новый** — каркас добавлен |
| **Wildberries KZ** | wildberries.kz | №2 маркетплейс | универсальный, электроника огромна | API `search.wb.ru` + `card.wb.ru`, но 403 Angie + WBAAS на пробе | **новый** — каркас |
| **Technodom** | technodom.kz | №1 специалист (~100 магазинов) | всё | JSON API открыт (`/katalog/api/v2`) | ✅ уже в ИС |
| **Sulpak** | sulpak.kz | №2 специалист (~120 магазинов) | всё | HTML + `Filter/LoadProducts` | ✅ |
| **Мечта** | mechta.kz | №3 специалист (~80) | всё | Cloudflare Turnstile (403 без браузера) | ✅ (через Playwright) |

### T2 — важно (расширяет покрытие)

| Магазин | Домен | Масштаб | Доступность | Статус |
|---------|-------|---------|-------------|--------|
| Alser | alser.kz | №4 специалист | 200 OK, Nuxt, `window.__NUXT__` | ✅ |
| Эврика | evrika.com | ~40 магазинов | 301 OK, `__NEXT_DATA__` | ✅ |
| Ozon KZ | ozon.kz | растёт, топ-15 | Composer API требует cookies `__Secure-abtn` | **новый** каркас |
| Satu.kz | satu.kz | №1 после Kaspi (Prom/EVO, 80k продавцов) | HTML + Prom API | **новый** каркас |
| Shop.kz (Белый Ветер) | shop.kz | старейший PC-ритейлер | Bitrix HTML, `/offers/<slug>/` | ✅ (как `shopkz`) |

### T3 — опционально / низкий приоритет

| Магазин | Почему не в ядре |
|---------|------------------|
| DNS Shop KZ (dns-shop.kz) | CF challenge, ~20 магазинов, дублирует ассортимент T1 |
| Marwin/Meloman (marwin.kz) | Magento, электроника ограничена |
| ForteMarket / Halyk Market | банковские маркетплейсы, мелкий ассортимент |
| Flip.kz | книги/DVD, не электроника |

Агрегатор: `kaspi.kz/shop/c/smartphones/` — по модели `Яндекс.Маркет`, один лот Kaspi покрывает 30–40k мерчантов.

## Техническая доступность (live 2026-09-22)

| Магазин | API | Парсинг | Защита | Метод |
|---------|-----|---------|--------|-------|
| Technodom | открыт JSON | отлично | нет | `context.request` → JSON |
| Sulpak | нет | да (HTML+sitemap) | нет | HTML |
| Alser | нет | да (`__NUXT__`) | нет | HTML |
| Эврика | нет | да (`__NEXT_DATA__`) | нет | HTML |
| Shop.kz | нет (404 на /api) | да (HTML) | diginetica | HTML |
| Kaspi | merchant API (auth) | частично (HTML) | JS-гидрат, без CF | HTML-parse category → product page |
| Satu | Prom API (merchant) | HTML | нет | HTML |
| Wildberries | `search.wb.ru` / `card.wb.ru` | API, но WBAAS antibot | 403 + challenge | API с `dest=-3623895&curr=kzt` + UA/cookies или официальный Supplier API |
| Ozon | composer API | требует cookies | 307 + app-check | headless или composer с сессией |
| Мечта/DNS | скрыт за CF | только headless | CF Turnstile | Playwright (уже так) |

Легче → сложнее: `Technodom > Sulpak > Shop.kz > Alser > Эврика > Kaspi > Satu > WB/Ozon > Мечта/DNS`.

`robots.txt` — у всех `/catalog`, `/f/`, `/c/`, `/shop/c/` **разрешены**, запрещены `/cart`, `/checkout`, `/compare`, `/my-account`.

## Решение по расширению ИС

**Уже покрыто 6 магазинов** — это 80% сравнимого ассортимента специалистов.

**Добавлено каркасами (включено, но с флагом `enabled=False` до настройки лимитов/куков):**
- `kaspi` — главный источник цены KZ, без него сравнение неполноценно. HTML-парсер категорий → карточки.
- `wildberries` — API `search.wb.ru` + `card.wb.ru` с `dest=-3623895`.
- `ozon` — composer API `ozon.kz/api/composer-api.bx/page/json/v2`.
- `satu` — HTML поиск/prom.
- `dns` — CF, через Playwright как `mechta` (отключён по умолчанию).

Каркасы не ломают обход: при `enabled=False` пропускаются, при включении — с rate-limit 1 req/s и ретраями.

## Юридические замечания

- Публичные цены — фактические данные, не PII, но ToS всех площадок запрещают «автоматизированный сбор».
- Минимизация риска: 1 req/s/домен, `User-Agent: SkidkiBot/1.0 (+https://.../bot-info)`, `429`/`Retry-After` уважать, кэш `If-Modified-Since`/`ETag`, не трогать `/cart`/`/checkout`.
- Kaspi / WB / Ozon имеют официальные Seller/Merchant API — для продакшн-мониторинга предпочтительнее их (стабильность + легальность).
- Обход CF Turnstile без браузера — не делать; для Мечты/DNS используем Playwright с реальным браузером.

## Что дальше

1. Включить `kaspi` первым — даёт максимальный прирост «честной цены» (медиана по мерчантам).
2. Затем `wildberries`/`ozon` — дают независимую точку отсчёта (маркетплейсная цена).
3. `satu`/`dns` — по мере необходимости для long-tail/PC-компонентов.
4. Метрика «честная скидка» = сравнение текущей цены с медианой 90 дней **и** с медианой Kaspi/WB цены — ловит рисованные зачёркивания.
