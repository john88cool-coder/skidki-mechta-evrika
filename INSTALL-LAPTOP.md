# Установка на ноутбук (mechta)

Гибридная схема 2026-09-18: пять магазинов (evrika, shop.kz, sulpak,
technodom, alser) обходятся в GitHub Actions, а **mechta.kz — только с этого
ноутбука**: сайт отдаёт 403 всем дата-центровым IP (GitHub и даже Decodo DC),
проверено пробами 2026-09-18.

Ноутбук держит:
- обход mechta каждые 2 часа (Планировщик Windows, задача `skidki-crawl`);
- слушатель кнопок Telegram (`skidki-bot`) — те же токен и чат, что в облаке;
- свою базу `data/skidki.sqlite3` — только mechta (создаётся скриптом ниже).

## 1. Установка

1. Распакуйте пакет в папку, например `C:\Shop_bot`.
2. Поставьте Python 3.12+ с [python.org](https://www.python.org/downloads/)
   (при установке отметьте **Add python.exe to PATH**).
3. В этой папке:
   ```powershell
   pip install -e ".[dev]"
   python -m playwright install chromium
   ```
4. Скопируйте `.env.example` в `.env` и впишите те же
   `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`, что в облаке.

## 2. База с историей mechta

Без истории сигналы «упало»/«минимум» молчат первые дни. Возьмите копию
прод-базы домашнего ПК и вычистите из неё всё, кроме mechta:

```powershell
python deploy/make_laptop_db.py --source data/skidki.sqlite3 --target data/laptop/skidki.sqlite3
```

Перенесите `data/laptop/skidki.sqlite3` на ноутбук в `data/skidki.sqlite3`.

## 3. Задачи Планировщика

Обход mechta каждые 2 часа (в :17), скрыто, будит ноутбук из сна:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install_task.ps1 -Shops mechta
```

Слушатель кнопок (группы уведомлений) — при входе в Windows, перезапуск
после сбоя:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install_bot_task.ps1
```

В плане электропитания разрешите **таймеры пробуждения**, иначе ноутбук не
проснётся для обхода.

## 4. Проверка

```powershell
skidki crawl --console --shop mechta
```

Логи: `logs\crawl-ДАТА.log` (обход), `logs\bot.log` (слушатель).

Удалить задачи:

```powershell
Unregister-ScheduledTask -TaskName skidki-crawl -Confirm:$false
Unregister-ScheduledTask -TaskName skidki-bot -Confirm:$false
```

## Ограничения схемы

- Кнопки «Группы уведомлений» и `/groups` управляют **только** сводками
  mechta (ноутбучная база). Облачные сводки шлют все группы — их база в кэше
  Actions с ноутбуком не связана.
- Один токен бота = один слушатель `getUpdates`: не запускайте `skidki bot`
  одновременно на двух машинах.
- Пропущенный запуск (ноутбук был выключен) выполнится при первой возможности.
