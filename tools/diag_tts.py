#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка озвучки через приложение: чат с TTS -> сколько аудио пришло.

    python tools/diag_tts.py "какое оборудование под кодом 3"
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import time

import websockets

URL = "ws://127.0.0.1:8000/ws"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
STOP_AFTER_FIRST = "--stop" in sys.argv      # проверить остановку воспроизведения
QUESTION = ARGS[0] if ARGS else "скажи коротко: поверка датчика давления"


async def main() -> int:
    chunks = 0
    audio = 0
    text = ""
    answer_done = False
    last_event = time.time()
    t0 = time.time()
    async with websockets.connect(URL, max_size=16 << 20) as ws:
        await ws.send(json.dumps({"type": "chat", "text": QUESTION, "tts": True, "rag": True}))
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=180)
            except asyncio.TimeoutError:
                # после ответа ждём аудио: синтез идёт асинхронно и может прийти позже
                if answer_done and time.time() - last_event > 8:
                    break
                if time.time() - t0 > 300:
                    print("таймаут ожидания")
                    break
                continue
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            last_event = time.time()
            if kind == "delta":
                text += msg.get("text", "")
            elif kind == "tts_chunk":
                chunks += 1
                audio += len(base64.b64decode(msg["wav"]))
                print(f"  аудио #{chunks}: {len(base64.b64decode(msg['wav'])) / 1024:.0f} КБ "
                      f"({msg.get('text', '')[:50]!r})")
                if STOP_AFTER_FIRST and chunks == 1:
                    print("  -> отправляю stop (остановка воспроизведения)")
                    await ws.send(json.dumps({"type": "stop"}))
            elif kind == "tts_end":
                print("  конец озвучки")
                if answer_done:
                    break
            elif kind == "done":
                answer_done = True
                text = msg.get("text") or text
                print("  ответ получен, ждём аудио…")
            elif kind == "error":
                print("  ошибка:", msg.get("text"))
    print()
    print(f"ответ: {text[:200]!r}")
    print(f"аудиофрагментов: {chunks}, всего {audio / 1024:.0f} КБ, время {time.time() - t0:.1f} с")
    if STOP_AFTER_FIRST:
        print("  остановка сработала" if chunks == 1 else
              f"  ВНИМАНИЕ: после stop пришло ещё {chunks - 1} фрагментов")
    return 0 if chunks else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
