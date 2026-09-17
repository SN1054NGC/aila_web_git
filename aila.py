#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точка входа: python aila.py  (полностью локально, без интернета)."""
from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Логи пишутся в файл (start через 1> logs\aila.out.log): принудительно UTF-8,
# иначе баннер уходит в кодировке консоли и файл получается смешанным.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass

from aila_core import __version__, config  # noqa: E402
from aila_core.app import app  # noqa: E402


def main() -> None:
    import uvicorn

    url = f"http://{config.HOST}:{config.PORT}"
    print("=" * 62)
    print(f"  АЙЛА {__version__}  |  локальный режим, без интернета")
    print("=" * 62)
    print(f"  GUI:        {url}")
    print(f"  LLM:        {config.LLM_URL} (llama-server, запускать start_llm.bat)")
    print(f"  RAG:        {config.RETRIEVAL}, топ-{config.TOP_K}, индекс {config.INDEX_CACHE.name}")
    print(f"  Модели:     {config.MODELS_DIR}")
    print(f"  TTS/STT:    {config.TTS_ENGINE} / {config.STT_ENGINE}")
    print("=" * 62)

    if config.OPEN_BROWSER:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
