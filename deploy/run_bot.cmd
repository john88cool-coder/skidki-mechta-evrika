@echo off
rem Слушатель Telegram (задача skidki-bot): кнопки и команды групп уведомлений.
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"
echo ===== %DATE% %TIME% start >> "logs\bot.log"
%PY% -m skidki.cli bot >> "logs\bot.log" 2>&1
echo ===== %DATE% %TIME% exit %ERRORLEVEL% >> "logs\bot.log"
rem Слушатель не должен завершаться: выход — сбой, Планировщик перезапустит.
exit /b 1
