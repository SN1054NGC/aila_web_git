#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замер модели: скорость обработки промпта, генерации и текст ответа.

    python tools/bench_llm.py "какое оборудование под кодом 3 и когда по нему ТО-3" 200

Промпт строится ровно так же, как в приложении (RAG + факты о дате + сводка документа),
чтобы сравнение моделей было честным.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aila_core import config                     # noqa: E402
from aila_core.llm import LLMClient              # noqa: E402
from aila_core.rag import RagEngine              # noqa: E402

QUESTION = sys.argv[1] if len(sys.argv) > 1 else "какое оборудование под кодом 3 и когда по нему ТО-3"
MAX_TOKENS = int(sys.argv[2]) if len(sys.argv) > 2 else 200


def main() -> int:
    rag = RagEngine()
    rag.ensure_loaded(config.sample_document())
    hits = rag.search(QUESTION, config.TOP_K)
    context = rag.build_context(hits)
    llm = LLMClient()
    messages = llm.build_messages(QUESTION, context, [], "ru", digest=rag.digest())
    prompt_chars = sum(len(m["content"]) for m in messages)

    with httpx.Client(timeout=15, trust_env=False) as client:
        try:
            props = client.get(f"{config.LLM_URL}/props").json()
        except Exception as exc:
            print("llama-server недоступен:", exc)
            return 1
    model = Path(props.get("model_path", "?")).name
    n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")

    print("=" * 76)
    print(f"МОДЕЛЬ : {model}")
    print(f"КОНТЕКСТ: {n_ctx}   ПРОМПТ: {prompt_chars} символов   ЗАПРОС: {MAX_TOKENS} токенов")
    print(f"ВОПРОС : {QUESTION}")
    print("-" * 76)

    payload = {
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": MAX_TOKENS,
        "cache_prompt": False,          # честно: без кэша промпта
        "chat_template_kwargs": {"enable_thinking": False},
        "stream_options": {"include_usage": True},
    }

    started = time.monotonic()
    first_at = None
    pieces: list[str] = []
    usage: dict = {}
    with httpx.Client(timeout=httpx.Timeout(15.0, read=900.0), trust_env=False) as client:
        with client.stream("POST", f"{config.LLM_URL}/v1/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                print("ошибка:", (resp.read()).decode("utf-8", "ignore")[:300])
                return 1
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                if not delta:
                    continue
                if first_at is None:
                    first_at = time.monotonic() - started
                pieces.append(delta)

    total = time.monotonic() - started
    answer = "".join(pieces).strip()
    gen_tokens = usage.get("completion_tokens") or len(pieces)
    prompt_tokens = usage.get("prompt_tokens") or 0

    print(f"первый токен      : {first_at:.1f} с" if first_at else "первый токен: —")
    print(f"всего             : {total:.1f} с")
    if prompt_tokens:
        print(f"токенов промпта   : {prompt_tokens}  -> обработка {prompt_tokens / max(first_at or 1, 0.01):.1f} ток/с")
    if first_at:
        print(f"токенов ответа    : {gen_tokens}  -> генерация {gen_tokens / max(total - first_at, 0.01):.1f} ток/с")
    print("-" * 76)
    print(answer[:800] or "(пустой ответ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
