@echo off
chcp 866 >nul
rem ============================================================
rem  Перезапуск слушателя кнопок Telegram (задача skidki-bot).
rem
rem  Нужен после правки .env - например, замены токена:
rem  токен читается только при старте процесса.
rem  Пауза нужна задаче, чтобы остановиться: Stop и Start впритык
rem  дают "операция не поддерживается".
rem ============================================================
echo Останавливаю слушателя...
powershell -NoProfile -Command "Stop-ScheduledTask -TaskName 'skidki-bot' -ErrorAction SilentlyContinue"
timeout /t 5 /nobreak >nul
echo Проверяю, что прошлый процесс завершился...
powershell -NoProfile -Command "$left = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*skidki.cli bot*' }); if ($left.Count -gt 0) { Write-Host ('Осталось процессов слушателя, жду ещё 10 секунд'); Start-Sleep -Seconds 10 }"
echo Запускаю слушателя...
powershell -NoProfile -Command "Start-ScheduledTask -TaskName 'skidki-bot'"
timeout /t 8 /nobreak >nul
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'skidki-bot' | Select-Object TaskName, State | Format-Table -AutoSize"
powershell -NoProfile -Command "$now = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*skidki.cli bot*' }); Write-Host ('Процессов слушателя: ' + $now.Count + ' (должен быть 1)')"
echo Последние строки лога (должно быть "слушатель запущен", без ошибок):
powershell -NoProfile -Command "Get-Content 'logs\bot.log' -Tail 3 -Encoding UTF8"
pause
