# Модели: что нужно, откуда и как проверить

Проект работает офлайн. Голосовые модели лежат в репозитории через **Git LFS**, языковая
модель в репозитории не хранится (GGUF 4.6 ГиБ — GitHub не принимает объекты больше 2 ГиБ):
она скачивается из официального репозитория модели одной командой. Манифест контрольных сумм:
`models/SHA256SUMS`, проверка: `.venv_311\Scripts\python.exe tools\verify_models.py`.

**Все ссылки на загрузку моделей собраны в одном месте — в релизе
[models-v2.6.1](../../releases/tag/models-v2.6.1).** Там же вложением лежит архив голосовых
моделей `aila-models-voices.zip` (428 МБ) — прямая ссылка:
https://github.com/SN1054NGC/aila_web_git/releases/download/models-v2.6.1/aila-models-voices.zip

## Языковая модель (обязательна)

| Файл | Размер | Где взять |
|---|---|---|
| `models/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | 4.58 ГиБ | **https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct-GGUF** |

Скачать и проверить хеш одной командой (докачка обрыва поддерживается):

```bat
.venv_311\Scripts\python.exe tools\fetch_llm_model.py
```

Скрипт качает `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` из этого репозитория модели в
`models/` и сверяет SHA256 с манифестом. Другие модели:

```bat
.venv_311\Scripts\python.exe tools\fetch_llm_model.py --repo <владелец/репозиторий> --file <файл.gguf>
.venv_311\Scripts\python.exe tools\fetch_llm_model.py --url https://.../model.gguf --target models/model.gguf
```

Модель распространяется под **собственной лицензией Яндекса** (`yandexgpt-5-lite-8b`), а не под
лицензией проекта: см. `THIRD_PARTY.md` и `licenses/yandexgpt-5-lite-8b-LICENSE.txt`.

Вместо неё можно взять любую GGUF-модель: укажите файл переменной `AILA_MODEL`, а если она
кладётся в `models/` — пересоберите манифест: `tools\make_models_manifest.py`.

## Речь: синтез (TTS) — в репозитории (LFS)

| Файл | Размер | Источник | Лицензия |
|---|---|---|---|
| `models/silero/v4_ru.pt` | 38.2 МБ | https://models.silero.ai/models/tts/ru/v4_ru.pt | MIT |
| `models/silero/v3_1_ru.pt` | 59 МБ | https://models.silero.ai/models/tts/ru/v3_1_ru.pt | MIT |
| `models/silero/v3_en.pt` | 54.5 МБ | https://models.silero.ai/models/tts/en/v3_en.pt | MIT |
| `models/piper/ru_RU-irina-medium.onnx` + `.json` | 60.3 МБ | rhasspy/piper-voices | MIT |

Все голосовые модели одним архивом (428 МБ) — во вложениях релиза
[models-v2.6.1](../../releases/tag/models-v2.6.1): `aila-models-voices.zip`.
| `models/piper/en_US-amy-medium.onnx` + `.json` | 60.3 МБ | rhasspy/piper-voices | MIT |

Silero — основной движок (голос `baya`, 24 кГц, как в первой версии), Piper — запасной.
Семейство переключается переменной `AILA_SILERO_FAMILY` (`v4_ru` по умолчанию, `v3_1_ru` — голос
первой версии; для него нужен пакет `omegaconf`).

## Речь: распознавание (STT) — в репозитории (LFS)

| Каталог | Размер | Источник | Лицензия |
|---|---|---|---|
| `models/vosk/vosk-model-small-ru-0.22/` | ~87 МБ | https://alphacephei.com/vosk/models | Apache-2.0 |
| `models/vosk/vosk-model-small-en-us-0.15/` | ~68 МБ | https://alphacephei.com/vosk/models | Apache-2.0 |

Если LFS-файлы не скачались при клоне, выполните `git lfs pull`.

## Движок запуска модели (llama.cpp)

`llama-server.exe` в репозиторий не входит (сборка под конкретное железо). Возьмите релиз
llama.cpp (MIT) и укажите каталог:

```bat
set AILA_LLAMA_DIR=D:\llama.cpp\build\bin
start_llm_cpu.bat
```

Параметры по умолчанию: `--ctx-size 4096 --n-gpu-layers 0` (CPU). На слабом ПК это ~7 токенов/с
генерации: ответ на 2–4 предложения занимает 40–70 секунд, первый токен ~50 секунд.

## Что можно добрать скриптом

```bat
.venv_311\Scripts\python.exe tools\fetch_models.py --all      :: голосовые модели и эмбеддинги
.venv_311\Scripts\python.exe tools\fetch_llm_model.py         :: языковая модель с Hugging Face
```

## Проверка

```bat
.venv_311\Scripts\python.exe tools\verify_models.py
```

Выводит по каждому файлу `ок` / `НЕТ` / `НЕ СОВПАЛО`. Если файла нет — он не установлен;
если не совпало — файл повреждён или это другая версия модели (пересоберите манифест).
В манифесте 37 файлов: голосовые модели (в репозитории, через LFS) и языковая модель
(её файл появится после `fetch_llm_model.py`).
