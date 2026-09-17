# -*- coding: utf-8 -*-
"""Проверка моделей по манифесту SHA256 (models/SHA256SUMS).

Запуск:
    .venv_311\Scripts\python.exe tools\verify_models.py
    .venv_311\Scripts\python.exe tools\verify_models.py --manifest models\SHA256SUMS
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aila_core import config

CHUNK = 4 << 20


def sha256_file(path: Path) -> str:
    """SHA256 файла (читаем частями: модели весят гигабайты)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_manifest(path: Path) -> list[tuple[str, str]]:
    """Пары (хеш, относительный путь) из манифеста."""
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            pairs.append((parts[0].upper(), parts[1].strip()))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка моделей по SHA256")
    parser.add_argument("--manifest", default="models/SHA256SUMS")
    parser.add_argument("--root", default=str(config.ROOT))
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = Path(args.root) / manifest
    if not manifest.exists():
        print(f"нет манифеста: {manifest}")
        return 2

    entries = read_manifest(manifest)
    print(f"файлов в манифесте: {len(entries)} (основание: {manifest})")
    ok = missing = bad = 0
    for expected, relative in entries:
        target = Path(args.root) / relative
        if not target.exists():
            missing += 1
            print(f"  НЕТ        {relative}")
            continue
        actual = sha256_file(target)
        if actual == expected:
            ok += 1
            print(f"  ок         {relative}")
        else:
            bad += 1
            print(f"  НЕ СОВПАЛО {relative}")
            print(f"             ожидалось {expected}")
            print(f"             получено  {actual}")
    print(f"\nитог: ок {ok}, нет {missing}, не совпало {bad}")
    return 0 if bad == 0 and missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
