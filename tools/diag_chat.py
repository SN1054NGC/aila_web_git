# -*- coding: utf-8 -*-
"""Проверка ответов после правок: статистика документа, сроки, тайминги."""
import asyncio, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import websockets
from aila_core.llm import LLMClient
from aila_core.rag import RagEngine
from aila_core import config

QUESTIONS = sys.argv[1:] or [
    "какое сегодня число",
    "какая неделя по счету",
    "какое оборудование под кодом 3 и когда по нему ТО-3",
]

async def ask(question: str, eng: RagEngine, llm: LLMClient) -> None:
    print("=" * 72)
    print("ВОПРОС:", question)
    hits = eng.search(question, config.TOP_K)
    ctx = eng.build_context(hits)
    msgs = llm.build_messages(question, ctx, [], "ru", digest=eng.digest())
    print(f"  фрагментов {len(hits)}, контекст {len(ctx)} симв., промпт {sum(len(m['content']) for m in msgs)} симв.")
    print(f"  в system есть факты: {'ФАКТЫ О ДОКУМЕНТЕ' in msgs[0]['content']}")
    async with websockets.connect("ws://127.0.0.1:8000/ws", max_size=8 << 20) as ws:
        await ws.send(json.dumps({"type": "chat", "text": question, "tts": False, "rag": True}))
        t0, first, sources, answer = time.time(), None, 0, ""
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=900)
            except asyncio.TimeoutError:
                break
            if isinstance(raw, bytes):
                continue
            m = json.loads(raw)
            if m["type"] == "sources":
                sources = len(m.get("items") or [])
            elif m["type"] == "delta" and first is None:
                first = time.time() - t0
            elif m["type"] == "done":
                answer = m.get("text") or ""
                break
            elif m["type"] == "error":
                print("  ОШИБКА:", m.get("text"))
        print(f"  источников {sources}; первый токен {first and round(first,1)} с; всего {round(time.time()-t0,1)} с")
        print("  ОТВЕТ:", answer.strip()[:400] or "(пусто)")

async def main() -> None:
    eng = RagEngine(); eng.ensure_loaded(config.sample_document())
    print("digest:", eng.digest())
    llm = LLMClient(); await llm.ensure_context()
    for q in QUESTIONS:
        await ask(q, eng, llm)

asyncio.run(main())
