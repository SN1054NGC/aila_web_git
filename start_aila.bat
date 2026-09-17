@echo off
chcp 65001 > nul
title Айла - сервер и GUI
cd /d "%~dp0"

set PY=%~dp0.venv_311\Scripts\python.exe
if not exist "%PY%" set PY=python

echo ============================================================
echo   АЙЛА - локальный запуск (интернет не нужен)
echo   GUI:  http://127.0.0.1:8000
echo   LLM:  http://127.0.0.1:8080  (запускать start_llm_cpu.bat)
echo ============================================================
echo.

set AILA_OPEN_BROWSER=1
"%PY%" "%~dp0aila.py"

echo.
echo Сервер завершил работу.
pause
