# Сторонние компоненты и их лицензии

Лицензия проекта (см. `LICENSE`) запрещает использование **кода и материалов Айлы**.
На перечисленные ниже компоненты она **не распространяется**: у каждого своя лицензия,
и именно её условия нужно соблюдать при использовании и распространении.

| Компонент | Что это | Лицензия / условия | Ссылка |
|---|---|---|---|
| **YandexGPT-5-Lite-8B-instruct** | языковая модель (GGUF), 4.7 ГБ | собственная лицензия Яндекса (`license_name: yandexgpt-5-lite-8b`): использование в исследовательских, некоммерческих и коммерческих целях при условиях соглашения; порог 10 млн выходных токенов в месяц требует отдельного согласования | https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct |
| **Silero Models (TTS)** | синтез речи, файлы `models/silero/*.pt` | MIT | https://github.com/snakers4/silero-models |
| **Vosk (STT)** | распознавание речи, `models/vosk/vosk-model-small-*` | Apache License 2.0 | https://alphacephei.com/vosk/models |
| **Piper (TTS, запасной)** | голоса `models/piper/*.onnx` | MIT (голоса rhasspy/piper-voices) | https://github.com/rhasspy/piper |
| **llama.cpp / llama-server** | движок запуска GGUF | MIT | https://github.com/ggml-org/llama.cpp |
| **FastAPI, Uvicorn, NumPy, pandas, openpyxl, websockets, httpx** | сервер и разбор Excel | MIT / BSD / Apache-2.0 (по пакету) | PyPI |
| **torch, torchaudio** | рантайм Silero | BSD-3-Clause | https://pytorch.org |
| **num2words** | числа словами | LGPL-2.1 | PyPI |

Оригинальный текст лицензии модели YandexGPT лежит в `licenses/yandexgpt-5-lite-8b-LICENSE.txt`
(скачивается из репозитория модели). При передаче весов модели третьим лицам прикладывайте
этот файл и соблюдайте условия Яндекса.

Если компонент не указан в таблице — смотрите лицензию в его собственном пакете/репозитории.
