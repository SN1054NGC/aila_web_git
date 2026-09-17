#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разовая загрузка офлайн-моделей Айлы (запускать ОДИН раз, когда есть интернет).

Дальше приложение работает полностью без сети. Скачивает ТОЛЬКО то, что нужно:
  * vosk  — распознавание речи (ru/en), ~45 МБ на язык
  * silero — синтез речи (ru/en), ~60 МБ на язык
  * piper — альтернативный лёгкий синтез (ONNX), ~60 МБ на голос
  * e5    — семантический поиск (опционально; по умолчанию используется BM25 без моделей)

Примеры:
    python tools/fetch_models.py --list
    python tools/fetch_models.py --only vosk
    python tools/fetch_models.py --all
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

# Загрузка моделей — единственный режим, где сеть разрешена.
for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
    os.environ[var] = "0"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aila_core import config  # noqa: E402

VOSK_MODELS = {
    "ru": ("vosk-model-small-ru-0.22",
           "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"),
    "en": ("vosk-model-small-en-us-0.15",
           "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
}

SILERO_MODELS = {
    "v4_ru.pt": ["https://models.silero.ai/models/tts/ru/v4_ru.pt",
                 "https://models.silero.ai/models/tts/ru/v3_1_ru.pt"],
    "v3_en.pt": ["https://models.silero.ai/models/tts/en/v3_en.pt"],
}

SILERO_REPO_ZIP = ("https://codeload.github.com/snakers4/silero-models/"
                    "zip/refs/heads/master")

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_VOICES = {
    "ru_RU-irina-medium": "/ru/ru_RU/irina/medium/ru_RU-irina-medium",
    "ru_RU-dmitri-medium": "/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium",
    "en_US-amy-medium": "/en/en_US/amy/medium/en_US-amy-medium",
    "en_US-lessac-medium": "/en/en_US/lessac/medium/en_US-lessac-medium",
}


def human(size: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


USER_AGENT = "aila-local/2.0"


def _remote_size(url: str) -> int:
    """Размер файла на сервере (0, если неизвестен)."""
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def download(url: str, target: Path, quiet: bool = False, attempts: int = 60) -> bool:
    """Скачивание с докачкой.

    Соединение до этих хостов часто рвётся на середине, поэтому файл пишется в
    <файл>.part, при обрыве запрос повторяется с заголовком Range и качает дальше,
    а не с нуля. Прогресс виден в консоли.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    total = _remote_size(url)
    if total and tmp.exists() and tmp.stat().st_size >= total:
        tmp.replace(target)
        if not quiet:
            print(f"    уже скачано: {human(total)}")
        return True

    for attempt in range(1, attempts + 1):
        done = tmp.stat().st_size if tmp.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if done:
            request.add_header("Range", f"bytes={done}-")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                mode = "ab" if (done and response.status == 206) else "wb"
                if mode == "wb":
                    done = 0
                with open(tmp, mode) as out:
                    while True:
                        chunk = response.read(1 << 18)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        if not quiet and total:
                            print(f"\r    {done * 100 / total:5.1f}%  "
                                  f"{human(done)} / {human(total)}", end="", flush=True)
            if not quiet and total:
                print()
        except Exception as exc:
            if not quiet:
                print(f"\n    обрыв на {human(done)} ({exc}); продолжаю…")
            time.sleep(2)
            continue

        if not total or done >= total:
            tmp.replace(target)
            if not quiet:
                print(f"    готово: {human(done)}")
            return True
        if attempt % 5 == 0 and not quiet:
            print(f"    попытка {attempt}: {human(done)} из {human(total)}")

    print(f"    не удалось скачать полностью: {human(tmp.stat().st_size if tmp.exists() else 0)}")
    return False


def fetch_vosk() -> None:
    print("[1/4] Vosk (распознавание речи)")
    for lang, (name, url) in VOSK_MODELS.items():
        folder = config.VOSK_DIR / name
        if folder.exists() and any(folder.iterdir()):
            print(f"  {lang}: уже есть ({folder.name})")
            continue
        archive = config.VOSK_DIR / f"{name}.zip"
        print(f"  {lang}: {url}")
        if not download(url, archive) and not archive.exists():
            continue
        print("    распаковка…")
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(config.VOSK_DIR)
        archive.unlink(missing_ok=True)
        print(f"  {lang}: готово -> {folder}")
    print("  подсказка: если имя каталога другое, укажите AILA_VOSK_RU / AILA_VOSK_EN")


def fetch_silero() -> None:
    print("[2/4] Silero TTS (синтез речи, torch)")
    for name, urls in SILERO_MODELS.items():
        target = config.SILERO_DIR / name
        if target.exists() and target.stat().st_size > 1_000_000:
            print(f"  {name}: уже есть")
            continue
        for url in urls:
            print(f"  {name}: {url}")
            if download(url, target):
                break

    # Локальная копия репозитория silero-models: нужна для офлайн-загрузки через
    # torch.hub.load_local (тот же путь, что и в старых рабочих исходниках).
    repo = config.SILERO_DIR / "repo"
    if not (repo / "hubconf.py").exists():
        archive = config.SILERO_DIR / "repo.zip"
        print(f"  репозиторий silero-models -> {repo}")
        if download(SILERO_REPO_ZIP, archive, quiet=True) or archive.exists():
            try:
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(config.SILERO_DIR / "repo_tmp")
                for item in (config.SILERO_DIR / "repo_tmp").iterdir():
                    shutil.move(str(item), str(repo))
                shutil.rmtree(config.SILERO_DIR / "repo_tmp", ignore_errors=True)
                archive.unlink(missing_ok=True)
            except Exception as exc:
                print(f"    не удалось распаковать: {exc}")
    else:
        print("  репозиторий silero-models: уже есть")

    # hubconf ищет .pt в кэше torch — заранее кладём туда копии
    try:
        import torch
        checkpoints = Path(torch.hub.get_dir()) / "checkpoints"
        checkpoints.mkdir(parents=True, exist_ok=True)
        for pt in config.SILERO_DIR.glob("*.pt"):
            shutil.copy2(pt, checkpoints / pt.name)
        print(f"  .pt скопированы в кэш torch: {checkpoints}")
    except Exception as exc:
        print(f"  кэш torch пропущен: {exc}")

    print("  готово. Проверка: python tools/diag_voice.py")


def fetch_piper() -> None:
    print("[3/4] Piper TTS (лёгкий ONNX-синтез, без torch)")
    for voice, prefix in PIPER_VOICES.items():
        onnx = config.PIPER_DIR / f"{voice}.onnx"
        conf = config.PIPER_DIR / f"{voice}.onnx.json"
        if onnx.exists() and conf.exists():
            print(f"  {voice}: уже есть")
            continue
        print(f"  {voice}")
        ok = download(f"{PIPER_BASE}{prefix}.onnx", onnx)
        download(f"{PIPER_BASE}{prefix}.onnx.json", conf)
        if not ok:
            print(f"    {voice}: не удалось")
    print("  готово. Нужен пакет: pip install piper-tts")


def fetch_e5() -> None:
    print("[4/4] e5-small (семантический поиск, опционально)")
    if config.EMBED_MODEL_DIR.exists() and any(config.EMBED_MODEL_DIR.iterdir()):
        print(f"  уже есть: {config.EMBED_MODEL_DIR}")
        return
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        print("  нужен пакет huggingface_hub (pip install huggingface_hub)")
        return
    try:
        snapshot_download("intfloat/multilingual-e5-small",
                          local_dir=str(config.EMBED_MODEL_DIR),
                          local_dir_use_symlinks=False)
        print(f"  готово -> {config.EMBED_MODEL_DIR}")
        print("  включить: set AILA_RETRIEVAL=chroma")
    except Exception as exc:
        print(f"  не удалось: {exc}")


def show() -> None:
    print("Каталог моделей:", config.MODELS_DIR)
    print("  vosk :", config.VOSK_DIR)
    print("  silero:", config.SILERO_DIR)
    print("  piper:", config.PIPER_DIR)
    print("  e5   :", config.EMBED_MODEL_DIR)
    print("Свободно на диске:", human(shutil.disk_usage(str(ROOT)).free))
    for lang in ("ru", "en"):
        print(f"  язык {lang}: vosk={bool(config.vosk_model_path(lang))} "
              f"piper={bool(config.piper_voice_path(lang))}")
    for name in SILERO_MODELS:
        print(f"  silero {name}: {(config.SILERO_DIR / name).exists()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузка офлайн-моделей Айлы")
    parser.add_argument("--all", action="store_true", help="скачать всё")
    parser.add_argument("--only", choices=["vosk", "silero", "piper", "e5"],
                        help="скачать только один набор")
    parser.add_argument("--list", action="store_true", help="показать, что уже есть")
    args = parser.parse_args()

    if args.list or not (args.all or args.only):
        show()
        if not (args.all or args.only):
            print("\nЗапустите: python tools/fetch_models.py --all")
        return

    if args.all or args.only == "vosk":
        fetch_vosk()
    if args.all or args.only == "silero":
        fetch_silero()
    if args.all or args.only == "piper":
        fetch_piper()
    if args.all or args.only == "e5":
        fetch_e5()
    print()
    show()


if __name__ == "__main__":
    main()
