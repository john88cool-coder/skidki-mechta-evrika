@echo off
chcp 866 >nul
rem ============================================================
rem  Ручной обход mechta: запускает задачу skidki-crawl.
rem
rem  Сбор занимает ~5 минут, сводка уходит в Telegram, лог
rem  пишется в logs\crawl-<дата>.log (самый свежий файл).
rem  Плановые обходы идут сами каждые 2 часа - этот файл для
rem  проверки "здесь и сейчас".
rem ============================================================
echo Запускаю обход mechta (задача skidki-crawl)...
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'skidki-crawl'"
timeout /t 5 /nobreak >nul
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'skidki-crawl' | Get-ScheduledTaskInfo | Format-List TaskName, LastRunTime, LastTaskResult"
echo.
echo Сбор идёт примерно 5 минут. Последние строки лога:
powershell -NoProfile -Command "$log = Get-ChildItem 'logs\crawl-*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Write-Host ('[' + $log.Name + ']'); Get-Content $log.FullName -Tail 3 -Encoding UTF8"
echo.
echo Полный лог: logs\crawl-*.log (самый свежий файл).
pause
