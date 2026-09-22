@echo off
rem Обход из Планировщика Windows (задача skidki-crawl).
rem Использование: run_crawl.cmd [shops] — список магазинов через запятую;
rem без аргумента обходятся все. Пример: run_crawl.cmd mechta
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG=logs\crawl-%TODAY%.log"
set "SHOP_ARGS="
if not "%~1"=="" call :shops %~1
echo ===== %DATE% %TIME% start shops=%~1 >> "%LOG%"
%PY% -m skidki.cli crawl %SHOP_ARGS% >> "%LOG%" 2>&1
echo ===== %DATE% %TIME% exit %ERRORLEVEL% >> "%LOG%"
rem Срез mechta — на панель (gh-pages/data/local): облако mechta не видит.
%PY% -m skidki.cli publish-local >> "%LOG%" 2>&1
rem Логи старше 14 дней не нужны.
forfiles /p logs /m crawl-*.log /d -14 /c "cmd /c del @path" >nul 2>&1
exit /b 0

:shops
if "%~1"=="" goto :eof
set "SHOP_ARGS=%SHOP_ARGS% --shop %~1"
shift
goto :shops
