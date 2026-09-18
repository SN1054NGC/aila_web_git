# -*- coding: utf-8 -*-
"""Единая конфигурация. Всё настраивается переменными окружения (префикс AILA_)."""
from __future__ import annotations

import os
from pathlib import Path

# ------------------------------------------------------------------ пути
ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("AILA_MODELS", ROOT / "models"))
DATA_DIR = ROOT / "data"
UPLOADS_DIR = ROOT / "uploads"
WEB_DIR = ROOT / "web"
RAG_DB_DIR = ROOT / "rag_db"
INDEX_CACHE = DATA_DIR / "rag_index.json"

for _d in (MODELS_DIR, DATA_DIR, UPLOADS_DIR, RAG_DB_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

# ------------------------------------------------------------------ сервер
HOST = os.environ.get("AILA_HOST", "127.0.0.1")
PORT = int(os.environ.get("AILA_PORT", "8000"))
OPEN_BROWSER = os.environ.get("AILA_OPEN_BROWSER", "0") == "1"

# ------------------------------------------------------------------ LLM (llama-server, локально)
LLM_URL = os.environ.get("AILA_LLM_URL", "http://127.0.0.1:8080")
LLM_TIMEOUT = float(os.environ.get("AILA_LLM_TIMEOUT", "600"))
# Бюджет промпта в символах (≈3 символа на токен для русского).
# Верхняя граница промпта в символах; реальный лимит считается от контекста llama-server.
PROMPT_CHAR_BUDGET = int(os.environ.get("AILA_PROMPT_BUDGET", "8000"))
# Сколько символов русского текста приходится на один токен (для оценки бюджета).
CHARS_PER_TOKEN = float(os.environ.get("AILA_CHARS_PER_TOKEN", "2.2"))
# Резерв токенов на шаблон чата и служебные поля.
TOKEN_RESERVE = int(os.environ.get("AILA_TOKEN_RESERVE", "256"))
# Если llama-server не сообщил размер контекста — считаем так.
CONTEXT_FALLBACK_TOKENS = int(os.environ.get("AILA_CTX", "4096"))
MAX_HISTORY_TURNS = int(os.environ.get("AILA_HISTORY_TURNS", "6"))
MAX_ANSWER_TOKENS = int(os.environ.get("AILA_MAX_TOKENS", "384"))
# Qwen3-подобные модели по умолчанию «думают» — для голосового ассистента это лишняя задержка.
DISABLE_THINKING = os.environ.get("AILA_NO_THINK", "1") == "1"
TEMPERATURE = float(os.environ.get("AILA_TEMPERATURE", "0.2"))
SYSTEM_PROMPT = os.environ.get(
    "AILA_SYSTEM_PROMPT",
    "Ты Айла — инженер-эксперт по системе измерений количества и качества нефти (СИКН).\n"
    "Отвечай кратко, по делу и только на основе предоставленных фрагментов документации.\n"
    "Если в документации нет ответа — честно скажи об этом, не выдумывай.\n"
    "Ссылайся на лист и строку документа. Отвечай на языке вопроса.",
)

# ------------------------------------------------------------------ RAG
RETRIEVAL = os.environ.get("AILA_RETRIEVAL", "bm25")   # bm25 | chroma
TOP_K = int(os.environ.get("AILA_TOP_K", "5"))
EMBED_MODEL_DIR = Path(os.environ.get("AILA_EMBED_DIR", MODELS_DIR / "e5-small"))
CHROMA_COLLECTION = "aila_docs"
MAX_UPLOAD_MB = int(os.environ.get("AILA_MAX_UPLOAD_MB", "64"))

# ------------------------------------------------------------------ TTS
# auto | silero | piper | none
# Первая версия проекта озвучивала голосом Silero (v3_1_ru, baya, 24 кГц) — он и оставлен
# основным; Piper работает как запасной, если Silero недоступен.
TTS_ENGINE = os.environ.get("AILA_TTS", "silero").lower()
SILERO_DIR = Path(os.environ.get("AILA_SILERO_DIR", MODELS_DIR / "silero"))
PIPER_DIR = Path(os.environ.get("AILA_PIPER_DIR", MODELS_DIR / "piper"))
TTS_MAX_CHUNK = int(os.environ.get("AILA_TTS_CHUNK", "220"))   # символов в одном фрагменте
TTS_SPEED = float(os.environ.get("AILA_TTS_SPEED", "1.0"))     # 0.8 .. 1.3
# Множитель пауз между фразами при озвучке (регулируется ползунком в интерфейсе)
TTS_PAUSE_SCALE = float(os.environ.get("AILA_TTS_PAUSE", "1.0"))
# Пауза после фразы, мс. «…» — заметная пауза (например, после пометки о номерах)
TTS_SILENCE_MS = {".": 260, "!": 240, "?": 240, ",": 120, ";": 180, ":": 160, "\n": 200,
                  "…": 550}

# Голоса: первый доступный из списка
# Голоса, которые показываем в интерфейсе
SILERO_VOICES = {
    "ru": ["baya", "aidar", "kseniya", "xenia", "eugene"],
    "en": ["en_21", "en_22", "en_56"],
}

# Голос первой версии — v3_1_ru:baya, поэтому он идёт первым.
# Семейство голоса: v4_ru — новее и полностью совместимо (тот же голос baya);
# v3_1_ru — ровно та модель, что была в первой версии, требует пакет omegaconf.
# Переключить: set AILA_SILERO_FAMILY=v3_1_ru
_SILERO_FAMILY_ORDER = {
    "v3_1_ru": [("v3_1_ru", v) for v in ("baya", "aidar", "kseniya", "xenia", "eugene")],
    "v4_ru": [("v4_ru", v) for v in ("baya", "kseniya", "aidar", "xenia", "eugene")],
}
_chosen_family = os.environ.get("AILA_SILERO_FAMILY", "v4_ru")
_ru_families = _SILERO_FAMILY_ORDER.get(_chosen_family, _SILERO_FAMILY_ORDER["v4_ru"])
_ru_families += [p for p in _SILERO_FAMILY_ORDER["v4_ru"] + _SILERO_FAMILY_ORDER["v3_1_ru"]
                 if p not in _ru_families]

SILERO_SPEAKERS = {
    "ru": [f"{family}:{voice}" for family, voice in _ru_families],
    "en": ["v3_en:en_21", "v3_en:en_22", "v3_en:en_56"],
}
# Частота дискретизации как в первой версии (Silero поддерживает 8000/24000/48000).
SILERO_SAMPLE_RATE = int(os.environ.get("AILA_SILERO_RATE", "24000"))
PIPER_VOICES = {
    "ru": ["ru_RU-irina-medium", "ru_RU-dmitri-medium", "ru_RU-denis-medium"],
    "en": ["en_US-amy-medium", "en_US-lessac-medium", "en_GB-alan-medium"],
}

# ------------------------------------------------------------------ STT
# auto | vosk | none
STT_ENGINE = os.environ.get("AILA_STT", "auto").lower()
VOSK_DIR = Path(os.environ.get("AILA_VOSK_DIR", MODELS_DIR / "vosk"))
VOSK_MODEL_RU = os.environ.get("AILA_VOSK_RU", "vosk-model-small-ru-0.22")
VOSK_MODEL_EN = os.environ.get("AILA_VOSK_EN", "vosk-model-small-en-us-0.15")
STT_SAMPLE_RATE = 16000
STT_SILENCE_MS = int(os.environ.get("AILA_STT_SILENCE_MS", "1200"))


def _first_existing(*candidates: Path) -> Path | None:
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return None


def vosk_model_path(lang: str) -> Path | None:
    name = VOSK_MODEL_RU if lang == "ru" else VOSK_MODEL_EN
    return _first_existing(VOSK_DIR / name, VOSK_DIR / lang)


def piper_voice_path(lang: str, name: str | None = None) -> tuple[Path, Path] | None:
    candidates = [name] if name else PIPER_VOICES.get(lang, [])
    for voice in candidates:
        if not voice:
            continue
        onnx = PIPER_DIR / f"{voice}.onnx"
        cfg = PIPER_DIR / f"{voice}.onnx.json"
        if onnx.exists():
            return onnx, cfg
    return None


def sample_document() -> Path | None:
    """Образец документа для диагностики: первый .xlsx в uploads/.

    Имя файла у каждой копии своё (рабочий документ или обезличенный образец),
    поэтому код не привязан к конкретному названию.
    """
    try:
        files = sorted(UPLOADS_DIR.glob("*.xlsx"))
    except OSError:
        return None
    return files[0] if files else None


def as_public_dict() -> dict:
    """То, что не страшно отдать в браузер."""
    return {
        "host": HOST,
        "port": PORT,
        "llm_url": LLM_URL,
        "retrieval": RETRIEVAL,
        "top_k": TOP_K,
        "tts_engine": TTS_ENGINE,
        "stt_engine": STT_ENGINE,
        "tts_speed": TTS_SPEED,
        "max_upload_mb": MAX_UPLOAD_MB,
    }
