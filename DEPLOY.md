# Айла 2.6.1 — рабочая сборка (локально, без интернета)

Приватный репозиторий проекта «Айла»: локальный голосовой ассистент по графику ТО/КМХ.
Работает полностью офлайн: языковая модель, синтез и распознавание речи — на этом же компьютере.

## Что в репозитории (только необходимое для работы)

```
aila.py                  точка входа (сервер + GUI на http://127.0.0.1:8000)
aila_core/               ядро: app, rag, kmhto, llm, tts, stt, clock, textnorm, accents, config
web/                     интерфейс: index.html, style.css, app.js, pcm-worklet.js
tools/                   инструменты: selftest, audit_document, make_example_document,
                         verify_models, make_models_manifest, fetch_models, fetch_llm_model, diag_*
data/accent_dict.json    словарь ударений (нужен для правильного произношения)
data/reference/          справка о формате документа (участвует в поиске)
models/                  голосовые модели (Git LFS): Silero, Piper, Vosk + SHA256SUMS
licenses/                текст лицензии языковой модели
start_aila.bat           запуск Айлы
start_llm_cpu.bat        запуск llama-server (CPU-режим)
start_all.bat            запуск всего сразу
requirements-local.txt   зависимости (голосовые — опционально)
mypy.ini                 настройки проверки типов
LICENSE                  лицензия: использование запрещено
THIRD_PARTY.md           лицензии сторонних компонентов
MODELS.md                какие модели нужны, откуда и их SHA256
```

## Что НЕ в репозитории (и почему)

* языковая модель (GGUF 4.6 ГиБ) — качается с
  https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct-GGUF скриптом
  `tools/fetch_llm_model.py` (GitHub не принимает объекты больше 2 ГиБ);
* документация и заметки о версиях (`README_LOCAL.md`, `VERSION`, `RELEASE-*.md`,
  `PROJECT_AUDIT.md`) — хранятся только в локальной копии проекта: в них есть сведения
  о рабочем документе;
* рабочие документы и любые выгрузки в `uploads/` — только локально (правила в `.gitignore`);
  приложение само создаёт пустую папку и наполняет индекс из загруженного файла;
* `.venv_311/`, `logs/`, `data/rag_index.json`, `rag_db/`, `snapshots/` — создаются на месте;
* файлы первой версии (`app.py`, `app_excel*.py`, `reranker_server.py`, черновики) — не нужны.

## Быстрый старт (Windows, Python 3.11)

```bat
git clone https://github.com/SN1054NGC/aila_web.git
cd aila_web
py -3.11 -m venv .venv_311
.venv_311\Scripts\python.exe -m pip install -r requirements-local.txt
rem голосовые модули (по желанию): silero/torch, vosk, piper-tts
git lfs pull                                             :: голосовые модели из LFS
.venv_311\Scripts\python.exe tools\fetch_llm_model.py  :: языковая модель с Hugging Face + SHA256
.venv_311\Scripts\python.exe tools\verify_models.py     :: проверить модели по SHA256
start_all.bat                                          :: llama-server + Айла + браузер
```

Свой документ кладётся в `uploads/` (или загружается через интерфейс), индекс собирается сам.
Если `llama-server.exe` лежит не рядом с проектом, укажите путь:

```bat
set AILA_LLAMA_DIR=D:\llama.cpp\build\bin
set AILA_MODEL=models\YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf
start_llm_cpu.bat
```

## Настройки (переменные окружения, префикс AILA_)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `AILA_MODEL` | первый `*.gguf` в `models/` | файл языковой модели |
| `AILA_LLAMA_DIR` | `llama.cpp` рядом с проектом | каталог с `llama-server.exe` |
| `AILA_MODELS` | `models` | каталог моделей (Silero, Vosk, Piper) |
| `AILA_HOST`, `AILA_PORT` | 127.0.0.1, 8000 | адрес интерфейса |
| `AILA_LLM_URL` | http://127.0.0.1:8080 | адрес llama-server |
| `AILA_TTS` | silero | `silero` | `piper` | `none` |
| `AILA_STT` | auto | `vosk` | `none` |
| `AILA_SILERO_FAMILY` | v4_ru | `v4_ru` или `v3_1_ru` (голос первой версии) |
| `AILA_RETRIEVAL` | bm25 | `bm25` или `chroma` |

## Проверки

```bat
.venv_311\Scripts\python.exe tools\selftest.py             :: HTTP + WebSocket
.venv_311\Scripts\python.exe tools\make_example_document.py :: обезличенный образец (для проверок)
.venv_311\Scripts\python.exe tools\audit_document.py       :: сверка разбора с Excel
.venv_311\Scripts\python.exe -m aila_core.kmhto            :: самотест парсера документа
.venv_311\Scripts\python.exe tools\diag_tts.py "привет"   :: синтез речи
.venv_311\Scripts\python.exe tools\verify_models.py        :: модели по SHA256
.venv_311\Scripts\python.exe -m mypy                       :: типы
```

## Данные и секреты

В репозитории нет рабочих документов, персональных данных, ключей и токенов — они хранятся
только локально (опись — в локальной папке проекта `local-only/PRIVATE.md`).
Правила `.gitignore` закрывают `uploads/*`, `data/rag_index.json`, `.env`, `secrets/`,
`*.key`, `*.pem`, `*.token`, `*.gguf`, `logs/`, `snapshots/`.

## Лицензия

Использование запрещено — см. `LICENSE`. Сторонние компоненты (модель YandexGPT, Silero,
Vosk, Piper, llama.cpp и зависимости) остаются под своими лицензиями — см. `THIRD_PARTY.md`.
