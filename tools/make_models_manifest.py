# -*- coding: utf-8 -*-
"""Сборка манифеста SHA256 для моделей: models/SHA256SUMS.

Запуск (из корня проекта):
    .venv_311\Scripts\python.exe tools\make_models_manifest.py
    .venv_311\Scripts\python.exe tools\make_models_manifest.py --extra "%AILA_MODEL%"

Пути в манифесте — относительно корня проекта, поэтому tools\\verify_models.py
проверяет файлы на месте без дополнительных настроек.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.verify_models import sha256_file

SKIP_DIRS = {"__pycache__", ".git"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
MODEL_SUFFIXES = {".pt", ".onnx", ".json", ".gguf", ".mdl", ".fst", ".ie", ". mat",
                  ".txt", ".conf", ".dubm", ".int", ".ipa", ".raw", ".syms"}


def collect(root: Path, extra: list[Path]) -> list[Path]:
    """Файлы моделей: всё из models/ (кроме манифеста) плюс явно указанные."""
    files: list[Path] = []
    models_dir = root / "models"
    if models_dir.exists():
        for path in sorted(models_dir.rglob("*")):
            if not path.is_file() or path.name == "SHA256SUMS":
                continue
            if any(part in SKIP_DIRS for part in path.parts) or path.name in SKIP_NAMES:
                continue
            files.append(path)
    files.extend(path for path in extra if path.is_file())
    return sorted({path.resolve() for path in files})


def manifest_path(path: Path, root: Path) -> str:
    """Путь в манифесте: файлы вне проекта кладутся в models/."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return f"models/{path.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Манифест SHA256 для моделей")
    parser.add_argument("--root", default=".")
    parser.add_argument("--extra", action="append", default=[],
                        help="дополнительные файлы (например, .gguf вне models/)")
    parser.add_argument("--out", default="models/SHA256SUMS")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    extra = [Path(item) if Path(item).is_absolute() else root / item for item in args.extra]
    files = collect(root, extra)
    if not files:
        print("не найдено ни одного файла моделей")
        return 1

    lines: list[str] = ["# SHA256 моделей проекта «Айла»",
                        "# Проверка: tools\\verify_models.py",
                        ""]
    total = 0
    for path in files:
        digest = sha256_file(path)
        total += path.stat().st_size
        lines.append(f"{digest}  {manifest_path(path, root)}")
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"файлов: {len(files)}, объём {total / (1 << 20):.1f} МБ")
    print(f"манифест: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
