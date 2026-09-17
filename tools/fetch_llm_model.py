# -*- coding: utf-8 -*-
"""Скачать языковую модель (GGUF) с Hugging Face и проверить SHA256.

Модель в репозитории не хранится: GitHub не принимает объекты больше 2 ГиБ,
поэтому скрипт качает файл напрямую из официального репозитория модели.

Репозиторий модели: https://huggingface.co/yandex/YandexGPT-5-Lite-8B-instruct-GGUF

Запуск (из корня проекта):
    .venv_311\Scripts\python.exe tools\fetch_llm_model.py
    .venv_311\Scripts\python.exe tools\fetch_llm_model.py --repo yandex/YandexGPT-5-Lite-8B-instruct-GGUF \
        --file YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf
    .venv_311\Scripts\python.exe tools\fetch_llm_model.py --url https://.../model.gguf

Докачка поддерживается: если файл оборвался, запустите снова — продолжит с места обрыва.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aila_core import config
from tools.verify_models import read_manifest, sha256_file

HF = "https://huggingface.co"
CHUNK = 1 << 20


def human(size: float) -> str:
    return f"{size / (1 << 30):.2f} ГиБ" if size >= (1 << 30) else f"{size / (1 << 20):.1f} МБ"


def remote_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD")
    request.add_header("User-Agent", "aila-fetch")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.headers.get("Content-Length") or 0)
    except (urllib.error.URLError, ValueError, OSError):
        return 0


def download(url: str, target: Path) -> None:
    """Скачать с докачкой: сервер Hugging Face поддерживает Range."""
    part = target.with_suffix(target.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0
    total = remote_size(url)
    if total and done == total:
        print("  уже скачано полностью")
    else:
        request = urllib.request.Request(url)
        request.add_header("User-Agent", "aila-fetch")
        if done:
            request.add_header("Range", f"bytes={done}-")
            print(f"  продолжаю с {human(done)} из {human(total) if total else '?'}")
        mode = "ab" if done else "wb"
        with urllib.request.urlopen(request, timeout=120) as response, part.open(mode) as out:
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if total:
                    percent = done * 100 // total
                    sys.stdout.write(f"\r  {percent:3d}%  {human(done)}")
                    sys.stdout.flush()
        sys.stdout.write("\n")
    part.replace(target)
    print("  файл:", target, human(target.stat().st_size))


def main() -> int:
    parser = argparse.ArgumentParser(description="Языковая модель с Hugging Face + проверка SHA256")
    parser.add_argument("--repo", default="yandex/YandexGPT-5-Lite-8B-instruct-GGUF")
    parser.add_argument("--file", default="YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf")
    parser.add_argument("--url", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    url = args.url or f"{HF}/{args.repo}/resolve/{args.revision}/{args.file}"
    target = Path(args.target or f"models/{args.file}")
    if not target.is_absolute():
        target = config.ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)

    print("источник:", url)
    print("назначение:", target)
    download(url, target)

    if args.no_verify:
        return 0
    manifest = config.ROOT / "models" / "SHA256SUMS"
    expected = {relative: digest for digest, relative in read_manifest(manifest)}
    relative = target.relative_to(config.ROOT).as_posix() if target.is_relative_to(config.ROOT) else target.name
    if relative not in expected:
        print("в манифесте нет записи для", relative, "- хеш не проверялся")
        return 0
    print("считаю SHA256 ...")
    actual = sha256_file(target)
    if actual == expected[relative]:
        print("SHA256 совпал:", actual)
        return 0
    print("SHA256 НЕ СОВПАЛ")
    print("  ожидалось", expected[relative])
    print("  получено ", actual)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
