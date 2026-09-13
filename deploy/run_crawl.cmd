@echo off
rem Обход mechta + evrika из Планировщика Windows (задача skidki-crawl).
rem mechta режет IP дата-центров GitHub, поэтому обход идёт с домашнего ПК.
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG=logs\crawl-%TODAY%.log"
echo ===== %DATE% %TIME% start >> "%LOG%"
%PY% -m skidki.cli crawl >> "%LOG%" 2>&1
echo ===== %DATE% %TIME% exit %ERRORLEVEL% >> "%LOG%"
rem Логи старше 14 дней не нужны.
forfiles /p logs /m crawl-*.log /d -14 /c "cmd /c del @path" >nul 2>&1
exit /b 0
