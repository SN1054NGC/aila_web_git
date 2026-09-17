#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Полная проверка голоса БЕЗ микрофона: TTS -> WAV -> распознавание (Vosk).

Запуск: python tools/diag_voice.py
Печатает: путь загрузки Silero, частоту, длительность, распознанный текст.
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aila_core import config          # noqa: E402
from aila_core import textnorm        # noqa: E402
from aila_core.stt import STTService  # noqa: E402
from aila_core.tts import TTSService  # noqa: E402

PHRASE = "Преобразователь расхода, ТО-3 двадцатого января. Поверка датчика давления."
OUT_WAV = ROOT / "logs" / "tts_test.wav"


def save_wav(pcm: bytes, rate: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)


def resample_16k(pcm: bytes, rate: int) -> bytes:
    """Простой ресемплер для проверки: 48/24 кГц -> 16 кГц (усреднение групп)."""
    if rate == config.STT_SAMPLE_RATE:
        return pcm
    data = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    ratio = rate / config.STT_SAMPLE_RATE
    out_len = max(1, int(len(data) / ratio))
    x_old = np.linspace(0.0, 1.0, len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, out_len, endpoint=False)
    out = np.interp(x_new, x_old, data)
    return out.astype("<i2").tobytes()


def main() -> int:
    print("=== 1. Синтез речи (TTS) ===")
    tts = TTSService()
    ok = tts.load()
    print("  статус:", json.dumps(tts.status(), ensure_ascii=False))
    if not ok:
        print("  TTS не поднялся — проверьте models/silero")
        tts_ok = False
    else:
        tts_ok = True
        prepared = tts.prepare_text(PHRASE, "ru")
        print("  текст для озвучки:", prepared[:160])
        pcm = tts.engine.synth(prepared, "ru")
        rate = tts.engine.sample_rate
        seconds = len(pcm) / 2 / rate
        print(f"  синтезировано: {len(pcm)/1024:.0f} КБ, {seconds:.2f} с, {rate} Гц")
        save_wav(pcm, rate, OUT_WAV)
        print("  файл:", OUT_WAV)

    print()
    print("=== 2. Распознавание речи (Vosk) ===")
    stt = STTService()
    print("  статус:", json.dumps(stt.status(), ensure_ascii=False))
    if not stt.status()["ready"]:
        print("  STT не поднялся — проверьте models/vosk")
        return 0 if tts_ok else 1
    if not tts_ok:
        print("  нечего распознавать (нет синтеза)")
        return 1

    pcm16 = resample_16k(pcm, rate)
    session = stt.session("ru")
    if not session.ready:
        print("  сессия не создана:", session.error)
        return 1
    finals: list[str] = []
    partials = 0
    step = 4000                                   # 125 мс на кусок
    for offset in range(0, len(pcm16), step):
        part, final = session.feed(pcm16[offset:offset + step])
        if part:
            partials += 1
        if final:
            finals.append(final)
    tail = session.finish()
    if tail:
        finals.append(tail)
    text = " ".join(finals).strip()
    print(f"  отправлено {len(pcm16)/2/16000:.2f} с аудио, промежуточных результатов: {partials}")
    print("  РАСПОЗНАНО:", text or "(пусто)")
    words_ok = sum(1 for w in ("расход", "давлен", "январ", "поверк") if w in text.lower())
    print(f"  ключевых слов найдено: {words_ok} из 4")
    return 0 if tts_ok and text else 1


if __name__ == "__main__":
    sys.exit(main())
