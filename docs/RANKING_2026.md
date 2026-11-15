# «Лучший товар» — метрика выбора · 2026-09

> Как ИС определяет, что товар — *лучшая покупка*, а не просто «самая большая цифра на ценнике».

## Принцип

Магазинная зачёркнутая цена — ненадёжна: её рисуют. ИС считает три независимые оценки и сводит в **Value Score (0–100)**.

### 1) Честная скидка — `fair_discount`

- История ИС (медиана 14 дней, взвешенная по отрезкам, минимум 3 дня) — считается в `evaluate.py` / `export.py`.
- **Межмагазинная медиана (`marketplace_median`):** сопоставление одной и той же модели по MPN или очищенной сигнатуре модели + памяти в `matching.py` среди 6 розничных сетей (`mechta`, `evrika`, `shopkz`, `sulpak`, `technodom`, `alser`) при наличии минимум в 2 магазинах.
- Формула в `scoring.py`: если доступны и собственная `fair_discount`, и скидка к `marketplace_median`, берётся консервативный минимум из двух.

### 2) Ценность — `value_score`

```
value = 100 * (0.55*fair_discount_norm + 0.20*brand_trust + 0.15*availability + 0.10*freshness) + external_bonus
```

- `fair_discount_norm` — `min(1.0, fair_discount / 40.0)`.
- `brand_trust` — `1.0` для `TRUSTED_BRANDS`, `0.5` для прочих известных брендов, `0.3` если бренд не указан.
- `availability` — в наличии без оговорок `= 1.0`, «на витрине»/«осталось мало»/«предзаказ» `= 0.6`, нет в наличии `= 0.0`.
- `freshness` — возраст наблюдения: `≤ 6 ч → 1.0`, `6–24 ч → 0.5`, `> 24 ч → 0.2` (неизвестно `→ 0.8`).

### 3) Внешние оценки — `external_bonus`

- Извлекаются парсерами (`mechta`, `technodom`, `alser`) и приводятся к шкале `0..5`.
- Если `rating ≥ 4.5` и `reviews_count ≥ 50`, начисляется бонус `+5.0` к `value_score` (с клипом до `100`).

## Бейджи в UI (`src/skidki/scoring.py`)

| Бейдж | Условие |
|-------|---------|
| **Выбор ИС** | `value_score ≥ 70` и `fair_discount ≥ 15%` и `price ≥ 20 000 ₸` и `in_stock` |
| **Честная скидка** | `fair_discount ≥ 15%` |
| **Топ-Бренд** | бренд входит в `TRUSTED_BRANDS` |
| **Рисованная?** | `shop_discount_pct − fair_discount ≥ 15 п.п.` |

## Где живут данные

- `Product` → поля `mpn`, `rating`, `reviews_count`.
- `matching.py` → `extract_mpn`, `model_key`, `marketplace_medians`.
- `export.py` → считает `marketplace_medians`, `value_score`, `fair_discount`, `is_pick` при экспорте `latest.json`.
- Фронтенд (`web/`) читает готовые метрики и отображает бейджи и вердикт истории.
