# -*- coding: utf-8 -*-
"""FastAPI-приложение Айлы: статика GUI, REST-API и WebSocket-сессия.

Всё работает локально: llama-server на 127.0.0.1, модели только из models/.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import clock
from . import config
from . import textnorm
from .llm import LLMClient
from .rag import RagEngine
from .stt import STTSession, STTService
from .tts import TTSService

log = logging.getLogger("aila")

WEB_DIR = config.WEB_DIR
WEB_DIR.mkdir(parents=True, exist_ok=True)

RAG = RagEngine()
TTS = TTSService()
STT = STTService()
LLM = LLMClient()

DEFAULT_XLSX = config.sample_document()      # первый xlsx в uploads/ (может не быть)
_SENT_TAIL = re.compile(r"^(.*?[.!?…])(\s+|$)", re.DOTALL)


def _warmup() -> None:
    """Фон: поднять индекс RAG и загрузить TTS, не блокируя старт сервера."""
    try:
        RAG.ensure_loaded(DEFAULT_XLSX)
        log.info("RAG: %s", RAG.status())
    except Exception as exc:
        log.warning("RAG не поднялся: %s", exc)
    try:
        TTS.load()
        log.info("TTS: %s", TTS.status())
    except Exception as exc:
        log.warning("TTS не поднялся: %s", exc)


def _quiet_asyncio(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Браузер часто рвёт keep-alive соединение — это не ошибка, не засоряем консоль."""
    if isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError)):
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    asyncio.get_running_loop().set_exception_handler(_quiet_asyncio)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx пишет строку на каждый опрос состояния — в консоли это лишний шум
    logging.getLogger("httpx").setLevel(logging.WARNING)
    threading.Thread(target=_warmup, name="aila-warmup", daemon=True).start()
    log.info("Айла запущена: http://%s:%s", config.HOST, config.PORT)
    yield
    await LLM.aclose()


app = FastAPI(title="Aila Local", version=__version__, lifespan=lifespan)


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/status")
async def api_status() -> JSONResponse:
    llm_ok = await LLM.health()
    return JSONResponse({
        "ok": True,
        "llm": {"ready": llm_ok, "url": config.LLM_URL, "model": await LLM.model_name_async(),
                "ctx": await LLM.ensure_context() if llm_ok else 0,
                "error": "" if llm_ok else LLM.last_error},
        "rag": RAG.status(),
        "tts": TTS.status(),
        "stt": STT.status(),
        "config": config.as_public_dict(),
    })


@app.get("/api/search")
async def api_search(q: str, k: int = 5) -> JSONResponse:
    hits = RAG.search(q, max(1, min(k, 20)))
    return JSONResponse({"query": q, "count": len(hits), "items": [
        {"id": h["id"], "score": h["score"], "kind": h["kind"],
         "sheet": h["meta"].get("sheet", ""), "row": h["meta"].get("row", 0),
         "code": h["meta"].get("code", ""), "equipment": h["meta"].get("equipment", ""),
         "text": h["text"]}
        for h in hits
    ]})


@app.post("/api/upload_excel")
async def api_upload(file: UploadFile = File(...)) -> JSONResponse:
    name = Path(file.filename or "file.xlsx").name
    if not name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return JSONResponse({"success": False, "error": "нужен файл .xlsx/.xls"}, status_code=400)
    target = config.UPLOADS_DIR / name
    size = 0
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        with open(target, "wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    out.close()
                    target.unlink(missing_ok=True)
                    return JSONResponse(
                        {"success": False,
                         "error": f"файл больше {config.MAX_UPLOAD_MB} МБ"},
                        status_code=413)
                out.write(chunk)
        stats = await asyncio.to_thread(RAG.build, target, name)
        return JSONResponse({"success": True, "file": name, "size": size, **stats})
    except Exception as exc:
        log.exception("ошибка индексации")
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.get("/api/voices")
async def api_voices() -> JSONResponse:
    return JSONResponse(TTS.available_voices())


@app.post("/api/rag/clear")
async def api_rag_clear() -> JSONResponse:
    return JSONResponse({"success": True, **RAG.clear()})


@app.post("/api/tts/reload")
async def api_tts_reload() -> JSONResponse:
    TTS._loaded = False           # noqa: SLF001  (ручная перезагрузка движка)
    ok = await asyncio.to_thread(TTS.load)
    return JSONResponse({"success": ok, **TTS.status()})


# ---------------------------------------------------------------------------
# WebSocket-сессия
# ---------------------------------------------------------------------------
class Session:
    """Одна вкладка браузера = одна сессия: своя история, свой микрофон, свой стоп."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.history: list[dict] = []
        self.cancel = asyncio.Event()
        self.send_lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.stt: STTSession | None = None
        self.stt_lang = "ru"
        self.tts_on = True
        self.rag_on = True
        self.lang = "auto"
        self.pause_scale = config.TTS_PAUSE_SCALE   # пауза между фразами (ползунок в GUI)
        self.keep_serials = False                   # читать ли заводские номера (только если спросили)
        self.voice: str = ""                        # выбранный голос (список в GUI)
        self.tts_queue: asyncio.Queue = asyncio.Queue()
        self.tts_worker: asyncio.Task | None = None

    # ------------------------------------------------------------- отправка
    async def send(self, payload: dict) -> None:
        async with self.send_lock:
            try:
                await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass

    async def send_bytes_safe(self, data: bytes) -> None:
        async with self.send_lock:
            try:
                await self.ws.send_bytes(data)
            except Exception:
                pass

    async def error(self, text: str) -> None:
        await self.send({"type": "error", "text": text})

    # ------------------------------------------------------------- запуск
    async def start(self) -> None:
        self.tts_worker = asyncio.create_task(self._tts_loop())
        await self.send({"type": "hello", "config": config.as_public_dict(),
                         "status": await self.collect_status()})

    async def collect_status(self) -> dict:
        llm_ok = await LLM.health()
        return {"llm": llm_ok, "ctx": LLM.n_ctx, "rag": RAG.status(),
                "tts": TTS.status(), "stt": STT.status()}

    async def shutdown(self) -> None:
        self.cancel.set()
        if self.task and not self.task.done():
            self.task.cancel()
        if self.tts_worker:
            await self.tts_queue.put(None)
            self.tts_worker.cancel()

    # ------------------------------------------------------------- приём
    async def handle_text(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        kind = msg.get("type", "")
        if kind == "chat":
            await self.start_chat(msg)
        elif kind == "stop":
            await self.stop()
        elif kind == "clear":
            self.history.clear()
            await self.send({"type": "cleared"})
        elif kind == "status":
            await self.send({"type": "status", **await self.collect_status()})
        elif kind == "stt_start":
            await self.stt_start(msg)
        elif kind == "stt_stop":
            await self.stt_stop()
        elif kind == "stt_cancel":
            self.stt = None                      # отмена: распознанный текст выбрасываем
            await self.send({"type": "stt_state", "state": "off"})
        elif kind == "speak":
            await self.queue_speech(msg.get("text", ""), msg.get("lang") or self.lang, final=True)
        elif kind == "tts_stop":
            await self.tts_flush()
        elif kind == "set":
            self.tts_on = bool(msg.get("tts", self.tts_on))
            self.rag_on = bool(msg.get("rag", self.rag_on))
            self.lang = msg.get("lang", self.lang)
            try:
                self.pause_scale = max(0.1, min(3.0, float(msg.get("pause_scale", self.pause_scale))))
            except (TypeError, ValueError):
                pass
            if "voice" in msg:
                self.voice = str(msg.get("voice") or "")

    async def handle_binary(self, data: bytes) -> None:
        if self.stt is None:
            return
        partial, final = await asyncio.to_thread(self.stt.feed, data)
        if partial:
            await self.send({"type": "stt_partial", "text": partial})
        if final:
            await self.send({"type": "stt_final", "text": final})

    # ------------------------------------------------------------- микрофон
    async def stt_start(self, msg: dict) -> None:
        lang = msg.get("lang") or "ru"
        if lang == "auto":
            lang = "ru"
        session = STT.session(lang)
        if not session.ready:
            await self.error(f"Микрофон недоступен: {session.error or STT.error}")
            await self.send({"type": "stt_state", "state": "off"})
            return
        self.stt = session
        self.stt_lang = lang
        await self.send({"type": "stt_state", "state": "on", "lang": lang})

    async def stt_stop(self) -> None:
        if self.stt is None:
            return
        text = await asyncio.to_thread(self.stt.finish)
        self.stt = None
        await self.send({"type": "stt_state", "state": "off"})
        if text:
            await self.send({"type": "stt_final", "text": text})

    # ------------------------------------------------------------- генерация
    async def start_chat(self, msg: dict) -> None:
        if self.task and not self.task.done():
            await self.stop()
        self.tts_on = bool(msg.get("tts", self.tts_on))
        self.rag_on = bool(msg.get("rag", self.rag_on))
        self.lang = msg.get("lang") or self.lang
        self.task = asyncio.create_task(self._run_chat(msg))

    async def stop(self) -> None:
        self.cancel.set()
        if self.task and not self.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=3)
            except Exception:
                self.task.cancel()
        await self.tts_flush()
        await self.send({"type": "stopped"})

    async def _run_chat(self, msg: dict) -> None:
        question = (msg.get("text") or "").strip()
        if not question:
            return
        lang = msg.get("lang") or self.lang
        if lang == "auto":
            lang = textnorm.detect_lang(question)
        self.cancel = asyncio.Event()
        # Заводские номера озвучиваем только если о них спросили в вопросе
        self.keep_serials = textnorm.asks_serials(question)
        await self.send({"type": "start", "lang": lang})

        # Вопросы про дату, день недели и номер недели отвечаем точно и мгновенно:
        # модель для этого не нужна, а на CPU её ответа пришлось бы ждать десятки секунд.
        quick = clock.answer(question, lang)
        if quick:
            log.info("календарный вопрос: %r -> %s", question[:60], quick)
            if self.tts_on:
                await self.queue_speech(quick, lang, final=True)
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": quick})
            self.history = self.history[-2 * config.MAX_HISTORY_TURNS * 2:]
            await self.send({"type": "done", "text": quick, "sources": []})
            return

        if not await LLM.health():
            await self.error("LLM-сервер недоступен. Запустите start_llm.bat "
                             f"({config.LLM_URL}).")
            await self.send({"type": "done", "text": "", "sources": []})
            return

        hits: list[dict] = []
        context = ""
        if self.rag_on and RAG.docs:
            hits = RAG.search(question, config.TOP_K)
            context = RAG.build_context(hits)
        if hits:
            await self.send({"type": "sources", "items": [
                {"id": h["id"], "score": h["score"], "kind": h["kind"],
                 "sheet": h["meta"].get("sheet", ""), "row": h["meta"].get("row", 0),
                 "code": h["meta"].get("code", ""),
                 "equipment": h["meta"].get("equipment", ""),
                 "preview": h["text"][:400]}
                for h in hits
            ]})

        await LLM.ensure_context()
        LLM.shrunk = False
        digest = RAG.digest() if (self.rag_on and RAG.docs) else ""
        messages = LLM.build_messages(question, context, self.history, lang, digest=digest)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        started = time.monotonic()
        log.info("вопрос: %r | фрагментов: %d | промпт: %d симв. | ctx: %d",
                 question[:80], len(hits), prompt_chars, LLM.n_ctx)
        await self.send({"type": "status", "phase": "generating", "ctx": LLM.n_ctx,
                         "prompt_chars": prompt_chars})
        buffer = ""
        first_token = True
        spoken_upto = 0

        async def on_delta(delta: str) -> None:
            nonlocal buffer, spoken_upto, first_token
            if first_token:
                first_token = False
                log.info("первый токен через %.1f с", time.monotonic() - started)
            buffer += delta
            await self.send({"type": "delta", "text": delta})
            if not self.tts_on:
                return
            # отправляем на озвучку по мере появления целых предложений
            while True:
                match = _SENT_TAIL.match(buffer[spoken_upto:])
                if not match:
                    break
                sentence = match.group(1).strip()
                spoken_upto += match.end(1)
                if len(sentence) >= 2:
                    await self.queue_speech(sentence, lang)

        try:
            answer = await LLM.stream_chat(messages, on_delta, self.cancel)
        except Exception as exc:
            log.warning("ошибка LLM: %s", exc)
            await self.error(f"Ошибка LLM: {exc}")
            answer = buffer
        else:
            tail = buffer[spoken_upto:].strip()
            if self.tts_on and tail:
                await self.queue_speech(tail, lang, final=True)
            elif self.tts_on:
                # всё уже отправлено на синтез: просим воркер сообщить, когда аудио закончится
                await self.tts_queue.put({"flush": True})

        log.info("ответ: %d символов за %.1f с", len(answer), time.monotonic() - started)
        if answer:
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "assistant", "content": answer})
            self.history = self.history[-2 * config.MAX_HISTORY_TURNS * 2:]
        await self.send({"type": "done", "text": answer,
                         "sources": [h["id"] for h in hits]})

    # ------------------------------------------------------------- озвучка
    async def queue_speech(self, text: str, lang: str, final: bool = False) -> None:
        if not text.strip():
            return
        if not TTS.ready:
            if final:
                await self.send({"type": "tts_end"})
            return
        await self.tts_queue.put({"text": text[:4000], "lang": lang, "final": final})

    async def tts_flush(self) -> None:
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        await self.send({"type": "tts_stop"})

    async def _tts_loop(self) -> None:
        """Последовательный синтез: порядок фрагментов важен."""
        while True:
            item = await self.tts_queue.get()
            if item is None:
                return
            if item.get("flush"):
                await self.send({"type": "tts_end"})
                continue
            if self.cancel.is_set():
                continue
            try:
                chunks = await asyncio.to_thread(TTS.chunks, item["text"], item["lang"],
                                                 self.pause_scale, self.voice or None,
                                                 self.keep_serials)
            except Exception as exc:
                log.warning("TTS: %s", exc)
                chunks = []
            for chunk in chunks:
                if self.cancel.is_set():
                    break
                await self.send({
                    "type": "tts_chunk",
                    "index": chunk["index"],
                    "wav": base64.b64encode(chunk["wav"]).decode("ascii"),
                    "text": chunk["text"],
                })
            if item.get("final"):
                await self.send({"type": "tts_end"})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session = Session(ws)
    await session.start()
    try:
        while True:
            message = await ws.receive()
            mtype = message.get("type")
            if mtype == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await session.handle_binary(message["bytes"])
            elif message.get("text") is not None:
                await session.handle_text(message["text"])
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.info("сессия закрыта: %s", exc)
    finally:
        await session.shutdown()


# статика GUI (в самом конце, чтобы не перекрыть /api и /ws)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
