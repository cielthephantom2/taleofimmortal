@echo off
chcp 65001 >nul
setlocal
set "TRANSLATOR_PYTHON=C:\Users\cielt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%TRANSLATOR_PYTHON%" set "TRANSLATOR_PYTHON=python"
set "TRANSLATOR_COMMAND=%~1"
if not defined TRANSLATOR_COMMAND set "TRANSLATOR_COMMAND=plan"
if /i "%TRANSLATOR_COMMAND%"=="audit" goto audit
if "%~2"=="" goto unlimited
"%TRANSLATOR_PYTHON%" -X utf8 "%~dp0translate.py" "%TRANSLATOR_COMMAND%" --config "%~dp0config.json" --limit "%~2"
exit /b %errorlevel%
:unlimited
"%TRANSLATOR_PYTHON%" -X utf8 "%~dp0translate.py" "%TRANSLATOR_COMMAND%" --config "%~dp0config.json"
exit /b %errorlevel%
:audit
"%TRANSLATOR_PYTHON%" -X utf8 "%~dp0audit_localtext.py"
exit /b %errorlevel%
