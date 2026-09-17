@echo off
chcp 65001 > nul
title Айла - локальный запуск
setlocal
cd /d "%~dp0"

echo [1/3] Проверяю llama-server на 127.0.0.1:8080 ...
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8080/health > "%TEMP%\aila_health.txt" 2>nul
set /p HEALTH=<"%TEMP%\aila_health.txt"
if not "%HEALTH%"=="200" (
    echo       запускаю модель отдельным окном...
    start "Айла LLM" cmd /c "%~dp0start_llm_cpu.bat"
    echo       жду загрузки модели (обычно 10-60 секунд)...
    :wait
    timeout /t 3 /nobreak > nul
    curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8080/health > "%TEMP%\aila_health.txt" 2>nul
    set /p HEALTH=<"%TEMP%\aila_health.txt"
    if not "%HEALTH%"=="200" goto wait
)
echo       LLM готов

echo [2/3] Запускаю Айлу на http://127.0.0.1:8000 ...
start "Айла" cmd /c "%~dp0start_aila.bat"
timeout /t 3 /nobreak > nul
start "" http://127.0.0.1:8000

echo [3/3] Готово. Окно можно закрыть - серверы работают отдельно.
pause
