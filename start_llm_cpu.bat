@echo off
chcp 65001 > nul
title Айла - LLM (llama-server, CPU)
setlocal
cd /d "%~dp0"

rem Каталог с llama-server.exe: рядом с проектом или задайте AILA_LLAMA_DIR
if not defined AILA_LLAMA_DIR set AILA_LLAMA_DIR=%~dp0llama.cpp
if not exist "%AILA_LLAMA_DIR%\llama-server.exe" (
    echo [!] Не найден llama-server.exe в "%AILA_LLAMA_DIR%"
    echo     Скачайте/соберите llama.cpp и укажите путь:
    echo         set AILA_LLAMA_DIR=D:\llama.cpp\build\bin
    pause
    exit /b 1
)

rem Модель: AILA_MODEL или первый *.gguf в models\
if not defined AILA_MODEL (
    for %%f in ("%~dp0models\*.gguf") do if not defined AILA_MODEL set AILA_MODEL=%%~ff
)
if not defined AILA_MODEL (
    echo [!] Не найдена модель: положите *.gguf в models\ или задайте AILA_MODEL
    echo     Список и хеши: MODELS.md
    pause
    exit /b 1
)

set CTX=%AILA_CTX%
if not defined CTX set CTX=4096

echo ============================================================
echo   АЙЛА - языковая модель (CPU-режим)
echo   движок: %AILA_LLAMA_DIR%\llama-server.exe
echo   модель: %AILA_MODEL%
echo   контекст: %CTX% токенов
echo ============================================================
echo.

"%AILA_LLAMA_DIR%\llama-server.exe" -m "%AILA_MODEL%" --host 127.0.0.1 --port 8080 ^
    --ctx-size %CTX% --threads %NUMBER_OF_PROCESSORS% --n-gpu-layers 0 ^
    --batch-size 1024 --ubatch-size 512

echo.
echo Сервер модели завершил работу.
pause
