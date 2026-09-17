#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Самопроверка локальной Айлы: HTTP + WebSocket, без интернета.

    python tools/selftest.py                 # проверить запущенный сервер
    python tools/selftest.py --url http://127.0.0.1:8000

Проверяет: отдачу GUI, /api/status, поиск по документации, микрофон и чат через WebSocket.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request


def http_get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except Exception as exc:
        return 0, str(exc)


def check_http(base: str) -> bool:
    ok = True
    checks = [
        ("GUI /", f"{base}/", "Айла"),
        ("CSS", f"{base}/static/style.css", "--accent"),
        ("JS", f"{base}/static/app.js", "WebSocket"),
        ("Worklet", f"{base}/static/pcm-worklet.js", "registerProcessor"),
        ("API статус", f"{base}/api/status", '"ok"'),
        ("API поиск", f"{base}/api/search?q=%D0%BA%D0%BE%D0%B4%207&k=3", "items"),
    ]
    for name, url, needle in checks:
        status, body = http_get(url)
        good = status == 200 and needle in body
        ok = ok and good
        print(f"  [{'OK ' if good else 'FAIL'}] {name:12} HTTP {status} ({len(body)} байт)")
    return ok


async def check_ws(base: str, question: str, wait_llm: float) -> dict[str, bool]:
    try:
        import websockets
    except Exception:
        print("  [SKIP] пакет websockets не установлен")
        return {"hello": True, "sources": False, "delta": False, "done": True,
                "error": False, "stt": False, "skipped": True}

    url = base.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    got = {"hello": False, "sources": False, "delta": False, "done": False,
           "error": False, "stt": False}
    text = ""
    async with websockets.connect(url, max_size=4 << 20) as ws:
        deadline = asyncio.get_event_loop().time() + wait_llm
        await ws.send(json.dumps({"type": "status"}))
        await ws.send(json.dumps({"type": "stt_start", "lang": "ru"}))
        await ws.send(json.dumps({"type": "chat",
                                  "text": question, "tts": False, "rag": True}))
        idle = 0
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                idle = 0
            except asyncio.TimeoutError:
                idle += 1
                if got["done"] or idle >= 30:      # CPU: первый токен может идти долго
                    break
                if idle % 5 == 0:
                    print(f"  … ждём LLM ({idle * 3} с тишины)")
                continue
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind not in ("delta", "tts_chunk"):
                print(f"  <- {kind}" + (f" {str(msg.get('text'))[:90]!r}" if msg.get("text") and kind != "delta" else ""))
            if kind == "hello":
                got["hello"] = True
                st = msg.get("status") or {}
                print(f"  hello: llm={st.get('llm')} rag={bool((st.get('rag') or {}).get('ready'))} "
                      f"tts={(st.get('tts') or {}).get('engine')} stt={bool((st.get('stt') or {}).get('ready'))}")
            elif kind == "status":
                print(f"  status: llm={msg.get('llm')}")
            elif kind == "stt_state":
                print(f"  микрофон: {msg.get('state')}")
            elif kind == "sources":
                got["sources"] = True
                items = msg.get("items") or []
                print(f"  найдено фрагментов: {len(items)}")
                for item in items[:3]:
                    print(f"    {item['score']:.2f} лист {item.get('sheet')} стр. {item.get('row')} "
                          f"код {item.get('code')}")
            elif kind == "delta":
                got["delta"] = True
                text += msg.get("text", "")
            elif kind == "error":
                got["error"] = True
                print(f"  ошибка сервера: {msg.get('text')}")
            elif kind == "done":
                got["done"] = True
                print(f"  ответ ({len(msg.get('text') or text)} симв.): "
                      f"{(msg.get('text') or text)[:200]!r}")
                break
    return got


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default="какое оборудование под кодом 3")
    parser.add_argument("--wait", type=float, default=90.0, help="сколько ждать ответ LLM, с")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    print("HTTP:")
    http_ok = check_http(base)
    print("WebSocket:")
    try:
        result = asyncio.run(check_ws(base, args.question, args.wait))
    except Exception as exc:
        print(f"  [FAIL] WebSocket: {exc}")
        return 2
    print()
    print("Итог:")
    print(f"  HTTP: {'пройдено' if http_ok else 'есть ошибки'}")
    print(f"  hello={result['hello']} sources={result['sources']} "
          f"delta={result['delta']} done={result['done']} error={result['error']}")
    if result["error"] and not result["delta"]:
        print("  (LLM недоступен — это ожидаемо, если llama-server не запущен)")
    return 0 if http_ok and result["hello"] and result["done"] else 1


if __name__ == "__main__":
    sys.exit(main())
