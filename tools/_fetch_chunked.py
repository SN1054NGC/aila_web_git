#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузка голосов для синтеза речи.

Разные хосты ведут себя по-разному:
  * HuggingFace (голоса Piper) — поддерживает Range, качаем чанками по 2 МБ;
  * models.silero.ai — Range НЕ поддерживает (отвечает 200 целиком), поэтому
    тянем файл одним потоком с повторами.

Уже скачанное не теряется: чанки дописываются, полный файл проверяется по размеру.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "aila-local/2.0"}
CHUNK = 2 << 20
CURL = "curl.exe"

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# url, путь, потоковый режим (Range)
FILES = [
    (f"{HF}/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx",
     "models/piper/ru_RU-irina-medium.onnx", True),
    (f"{HF}/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json",
     "models/piper/ru_RU-irina-medium.onnx.json", True),
    (f"{HF}/en/en_US/amy/medium/en_US-amy-medium.onnx",
     "models/piper/en_US-amy-medium.onnx", True),
    (f"{HF}/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
     "models/piper/en_US-amy-medium.onnx.json", True),
    ("https://models.silero.ai/models/tts/ru/v3_1_ru.pt", "models/silero/v3_1_ru.pt", False),
    ("https://models.silero.ai/models/tts/ru/v4_ru.pt", "models/silero/v4_ru.pt", False),
    ("https://models.silero.ai/models/tts/en/v3_en.pt", "models/silero/v3_en.pt", False),
]


def remote_size(url: str) -> int:
    try:
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def mb(value: float) -> str:
    return f"{value / 1048576:.1f} МБ"


def curl(args: list[str], timeout: int = 900) -> int:
    try:
        return subprocess.run([CURL, *args], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout).returncode
    except Exception:
        return -1


def fetch_ranged(url: str, out: Path, total: int) -> bool:
    done = out.stat().st_size if out.exists() else 0
    if total and done >= total:
        print(f"  {out.name}: уже скачан ({mb(total)})")
        return True
    if total:
        print(f"  {out.name}: {mb(total)}" + (f" (продолжаю с {mb(done)})" if done else ""))
    tmp = out.with_suffix(out.suffix + ".chunk")
    while total == 0 or done < total:
        end = done + CHUNK - 1
        if total:
            end = min(end, total - 1)
        for attempt in range(1, 7):
            rc = curl(["-L", "-s", "--max-time", "180", "-r", f"{done}-{end}",
                       "-o", str(tmp), url], timeout=240)
            if rc == 0 and tmp.exists() and tmp.stat().st_size > 0:
                with open(out, "ab") as out_handle, open(tmp, "rb") as chunk_handle:
                    shutil.copyfileobj(chunk_handle, out_handle)
                done += tmp.stat().st_size
                if total:
                    print(f"\r    {done * 100 / total:5.1f}%  {mb(done)}", end="", flush=True)
                break
            print(f"\n    сбой на {mb(done)}, повтор {attempt}")
            time.sleep(2)
        else:
            return False
        if total == 0:
            break
    tmp.unlink(missing_ok=True)
    print()
    return bool(done)


def fetch_stream(url: str, out: Path, total: int) -> bool:
    """Хост без поддержки Range: тянем целиком, при обрыве начинаем заново."""
    if total and out.exists() and out.stat().st_size == total:
        print(f"  {out.name}: уже скачан ({mb(total)})")
        return True
    if total:
        print(f"  {out.name}: {mb(total)} (без докачки — хост не поддерживает Range)")
    for attempt in range(1, 8):
        if out.exists():
            out.unlink()
        rc = curl(["-L", "-s", "--max-time", "1500", "-o", str(out), url], timeout=1600)
        size = out.stat().st_size if out.exists() else 0
        if rc == 0 and size and (not total or size == total):
            print(f"    готово: {mb(size)}")
            return True
        print(f"    попытка {attempt}: {mb(size)} из {mb(total)} — повтор")
        time.sleep(3)
    return False


def main() -> int:
    ok = True
    for url, rel, ranged in FILES:
        out = ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        total = remote_size(url)
        if ranged:
            ok = fetch_ranged(url, out, total) and ok
        else:
            ok = fetch_stream(url, out, total) and ok
    print("все файлы на месте" if ok else "часть файлов не скачалась")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
