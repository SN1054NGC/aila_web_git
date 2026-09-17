# -*- coding: utf-8 -*-
"""
Офлайн-режим и совместимость. Импортировать ПЕРВЫМ (до numpy/chroma/hf).

Задача модуля:
  1) полностью запретить любые сетевые загрузки моделей во время работы;
  2) отключить телеметрию;
  3) починить несовместимость chromadb 0.4.x с numpy 2.x;
  4) ограничить число потоков, чтобы не задушить слабый CPU.
"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def setup_offline() -> None:
    """Запрещаем сети и телеметрию. Вызывать до импорта chroma/torch/transformers."""
    # --- телеметрия ---
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")
    os.environ.setdefault("POSTHOG_DISABLED", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    # --- никакого интернета для моделей ---
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    # --- CPU: не забирать все ядра (на слабом ПК это важно) ---
    threads = _int_env("AILA_THREADS", max(1, (os.cpu_count() or 4) // 2))
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(var, str(threads))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def patch_numpy() -> None:
    """chromadb 0.4.x использует np.float_ / np.int_ / np.uint, удалённые в numpy 2.x."""
    try:
        import numpy as np
    except Exception:  # numpy может отсутствовать — не критично
        return
    if not hasattr(np, "float_"):
        np.float_ = np.float64  # type: ignore[attr-defined]
    if not hasattr(np, "int_"):
        np.int_ = np.int64  # type: ignore[attr-defined]
    if not hasattr(np, "uint"):
        np.uint = np.uint64  # type: ignore[attr-defined]
    if not hasattr(np, "unicode_"):
        np.unicode_ = np.str_  # type: ignore[attr-defined]


setup_offline()
