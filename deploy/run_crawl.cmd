@echo off
rem Обход из Планировщика Windows (задача skidki-crawl).
setlocal
cd /d "%~dp0.."
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PY=uv run python"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
) else (
    set "PY=py -3"
)
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG=logs\crawl-%TODAY%.log"
set "SHOP_ARGS="
if not "%~1"=="" call :shops %~1
echo ===== %DATE% %TIME% start shops=%~1 >> "%LOG%"
%PY% -m skidki.cli crawl %SHOP_ARGS% >> "%LOG%" 2>&1
set "CRAWL_RC=%ERRORLEVEL%"
echo ===== %DATE% %TIME% exit %CRAWL_RC% >> "%LOG%"
if %CRAWL_RC% EQU 0 (
    %PY% -m skidki.cli publish-local >> "%LOG%" 2>&1
)
forfiles /p logs /m crawl-*.log /d -14 /c "cmd /c del @path" >nul 2>&1
exit /b %CRAWL_RC%

:shops
if "%~1"=="" goto :eof
set "SHOP_ARGS=%SHOP_ARGS% --shop %~1"
shift
goto :shops
