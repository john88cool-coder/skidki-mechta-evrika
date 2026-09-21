@echo off
chcp 866 >nul
rem ============================================================
rem  Состояние задач (обход mechta, слушатель Telegram)
rem  и хвосты свежих логов. Ничего не меняет, только смотрит.
rem ============================================================
echo --- задачи ---
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'skidki-crawl','skidki-bot' | Select-Object TaskName, State | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'skidki-crawl','skidki-bot' | Get-ScheduledTaskInfo | Select-Object TaskName, LastRunTime, LastTaskResult, NextRunTime | Format-Table -AutoSize"
echo --- хвост свежего лога обхода ---
powershell -NoProfile -Command "$log = Get-ChildItem 'logs\crawl-*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Write-Host ('[' + $log.Name + ']'); Get-Content $log.FullName -Tail 5 -Encoding UTF8"
echo --- хвост лога слушателя ---
powershell -NoProfile -Command "Get-Content 'logs\bot.log' -Tail 5 -Encoding UTF8"
pause
