# Айла — локальный офлайн-ассистент

Голосовой ассистент по графику ТО/КМХ: отвечает по загруженному документу, озвучивает ответ
и понимает вопрос с микрофона. Работает полностью офлайн — языковая модель, синтез и
распознавание речи крутятся на этом же компьютере, интернет нужен только один раз, чтобы
скачать модели.

Интерфейс: `http://127.0.0.1:8000` после запуска.

## Скачать модели

| Что | Размер | Ссылка |
|---|---|---|
| **Языковая модель** (YandexGPT-5-Lite-8B-instruct, GGUF) | 4.7 ГБ | [репозиторий модели](https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct-GGUF) · [прямая ссылка на файл](https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct-GGUF/resolve/main/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf) |
| Голосовые модели (Silero, Piper, Vosk) | 428 МБ | в этом репозитории через Git LFS: `git lfs pull` · либо архив во вкладке [Releases](../../releases) |
| Движок запуска модели (llama.cpp, llama-server) | ~50 МБ | [релизы llama.cpp](https://github.com/ggml-org/llama.cpp/releases) |
| Silero TTS (если ставить отдельно) | 38 МБ | [v4_ru.pt](https://models.silero.ai/models/tts/ru/v4_ru.pt) |
| Vosk STT, русский | 44 МБ | [vosk-model-small-ru-0.22.zip](https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip) |
| Голос Piper, русский | 60 МБ | [ru_RU-irina-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx) |

Языковая модель в git не хранится: GitHub не принимает файлы больше 2 ГиБ, поэтому её берут
по ссылке выше. Скачать и проверить её одной командой (докачка обрыва поддерживается):

```bat
.venv_311\Scripts\python.exe tools\fetch_llm_model.py
.venv_311\Scripts\python.exe tools\verify_models.py
```

## Быстрый старт (Windows, Python 3.11)

```bat
git clone https://github.com/SN1054NGC/aila_web_git.git
cd aila_web_git
py -3.11 -m venv .venv_311
.venv_311\Scripts\python.exe -m pip install -r requirements-local.txt
git lfs pull                                              :: голосовые модели
.venv_311\Scripts\python.exe tools\fetch_llm_model.py   :: языковая модель
start_all.bat                                             :: llama-server + Айла + браузер
```

Свой документ (xlsx) кладётся в `uploads/` или загружается через интерфейс — индекс соберётся сам.
Путь к `llama-server.exe` задаётся переменной `AILA_LLAMA_DIR`, файл модели — `AILA_MODEL`
(подробности в DEPLOY.md).

## Что в репозитории

```
aila.py            точка входа (сервер + GUI)
aila_core/         ядро: разбор документа, поиск, модель, речь, произношение
web/               интерфейс (без внешних библиотек и CDN)
tools/             инструменты: проверки, диагностика, загрузка моделей
data/              словарь ударений и краткая справка о формате документа
models/            голосовые модели (Git LFS)
DEPLOY.md          установка, настройки, проверки
MODELS.md          модели: что, откуда, контрольные суммы
LICENSE            лицензия: использование запрещено
THIRD_PARTY.md     лицензии сторонних компонентов
```

## Проверки

```bat
.venv_311\Scripts\python.exe tools\selftest.py      :: сервер и WebSocket
.venv_311\Scripts\python.exe -m aila_core.kmhto      :: разбор документа
.venv_311\Scripts\python.exe tools\diag_tts.py "привет"
.venv_311\Scripts\python.exe -m mypy                 :: типы
```

## Лицензии

Использование кода и материалов проекта запрещено — см. [LICENSE](LICENSE).
Модели и библиотеки остаются под своими лицензиями: языковая модель — по лицензии Яндекса,
Silero — MIT, Vosk — Apache-2.0, Piper — MIT, llama.cpp — MIT. Подробности в
[THIRD_PARTY.md](THIRD_PARTY.md).

В репозитории нет рабочих документов, персональных данных, ключей и токенов — они хранятся
только локально у владельца.
