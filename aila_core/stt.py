# -*- coding: utf-8 -*-
"""Распознавание речи офлайн через Vosk (потоковый, лёгкий, без интернета).

Vosk принимает PCM 16 кГц/моно/int16 — именно это присылает браузер, поэтому
никакие ffmpeg/конвертеры не нужны.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config

try:  # необязательная зависимость: без неё приложение работает, просто без микрофона
    import vosk  # type: ignore
    HAS_VOSK = True
except Exception:
    vosk = None  # type: ignore
    HAS_VOSK = False


class STTService:
    """Держит загруженные модели Vosk (по одной на язык) и выдаёт сессии распознавания."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._lock = threading.Lock()
        self.error: str = ""
        if not HAS_VOSK:
            self.error = "пакет vosk не установлен (pip install vosk)"

    # ------------------------------------------------------------------ статус
    def available_langs(self) -> list[str]:
        if not HAS_VOSK:
            return []
        return [lang for lang in ("ru", "en") if config.vosk_model_path(lang) is not None]

    def status(self) -> dict:
        langs = self.available_langs()
        return {
            "ready": bool(langs),
            "engine": "vosk" if HAS_VOSK else "none",
            "langs": langs,
            "error": self.error if not langs else "",
        }

    # ------------------------------------------------------------------ модели
    def _model(self, lang: str) -> object:
        if lang in self._models:
            return self._models[lang]
        path = config.vosk_model_path(lang)
        if path is None:
            raise RuntimeError(
                f"нет модели Vosk для языка '{lang}'. Ожидается каталог "
                f"{config.VOSK_DIR} (см. tools/fetch_models.py)")
        with self._lock:
            if lang not in self._models:
                self._models[lang] = vosk.Model(str(path))
        return self._models[lang]

    def warmup(self, lang: str = "ru") -> bool:
        try:
            self._model(lang)
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

    # ------------------------------------------------------------------ сессии
    def session(self, lang: str = "ru") -> "STTSession":
        return STTSession(self, lang)


class STTSession:
    """Одно распознавание: кормим PCM — получаем partial/final."""

    def __init__(self, service: STTService, lang: str) -> None:
        self.service = service
        self.lang = lang
        self.error = ""
        self._closed = False
        self._rec = None
        try:
            model = service._model(lang)
            self._rec = vosk.KaldiRecognizer(model, config.STT_SAMPLE_RATE)
            self._rec.SetWords(False)
        except Exception as exc:
            self.error = str(exc)

    @property
    def ready(self) -> bool:
        return self._rec is not None

    def feed(self, pcm: bytes) -> tuple[str | None, str | None]:
        """Возвращает (partial, final). Любое из значений может быть None."""
        if not self._rec or self._closed:
            return None, None
        try:
            if self._rec.AcceptWaveform(pcm):
                text = (json.loads(self._rec.Result()).get("text") or "").strip()
                return None, (text or None)
            partial = (json.loads(self._rec.PartialResult()).get("partial") or "").strip()
            return (partial or None), None
        except Exception as exc:
            self.error = str(exc)
            return None, None

    def finish(self) -> str:
        if not self._rec or self._closed:
            return ""
        self._closed = True
        try:
            return (json.loads(self._rec.FinalResult()).get("text") or "").strip()
        except Exception:
            return ""
