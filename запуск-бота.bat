@echo off
chcp 866 >nul
rem ============================================================
rem  Запуск слушателя кнопок Telegram (задача skidki-bot).
rem
rem  Обычно он стартует сам при входе в Windows. Этот файл -
rem  чтобы поднять его вручную (после долгого сна ПК и т.п.).
rem  После правки .env используйте перезапуск-бота.bat:
rem  токен читается только при старте.
rem ============================================================
echo Запускаю слушателя Telegram (задача skidki-bot)...
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'skidki-bot'"
timeout /t 5 /nobreak >nul
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'skidki-bot' | Select-Object TaskName, State | Format-Table -AutoSize"
echo Последние строки лога (ошибок быть не должно):
powershell -NoProfile -Command "Get-Content 'logs\bot.log' -Tail 3 -Encoding UTF8"
pause
