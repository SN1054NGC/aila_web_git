# -*- coding: utf-8 -*-
"""Клиент локального llama-server: chat-completions со стримингом и бюджетом контекста.

Важно для слабого ПК: размер промпта считается от РЕАЛЬНОГО контекста сервера
(запрашивается у /props), иначе llama-server отвечает 400 и ответа нет вовсе.
Если контекст всё равно переполнен — промпт автоматически урезается и запрос повторяется.
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

import httpx

from . import clock
from . import config

DeltaCB = Callable[[str], Awaitable[None]]


def base_system_prompt(lang: str = "ru") -> str:
    if lang == "en":
        return ("You are Aila, an expert engineer on crude-oil quantity and quality "
                "measurement systems (SIKN). Answer briefly and only from the provided "
                "documentation excerpts. If the answer is not there, say so honestly. "
                "Cite the sheet and row number. Answer in the language of the question.")
    return config.SYSTEM_PROMPT


class LLMClient:
    """Общение с llama-server по HTTP. Только 127.0.0.1, интернет не нужен."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or config.LLM_URL).rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self.last_error: str = ""
        self.model_name: str = ""
        self.n_ctx: int = 0
        self.shrunk: bool = False      # был ли промпт урезан (для диагностики)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(connect=5.0, read=config.LLM_TIMEOUT, write=30.0, pool=5.0)
            self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ статус
    async def health(self) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/health", timeout=4.0)
            if resp.status_code == 200:
                self.last_error = ""
                return True
            self.last_error = f"HTTP {resp.status_code}"
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    async def model_name_async(self) -> str:
        if self.model_name:
            return self.model_name
        try:
            resp = await self.client.get(f"{self.base_url}/v1/models", timeout=4.0)
            items = (resp.json() or {}).get("data") or []
            if items:
                self.model_name = items[0].get("id", "")
        except Exception:
            pass
        return self.model_name

    async def detect_context(self) -> int:
        """Реальный размер контекста из llama-server (/props)."""
        if self.n_ctx:
            return self.n_ctx
        for path in ("/props", "/v1/props"):
            try:
                resp = await self.client.get(f"{self.base_url}{path}", timeout=4.0)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                gen = data.get("default_generation_settings") or {}
                value = gen.get("n_ctx") or data.get("n_ctx") or 0
                if value:
                    self.n_ctx = int(value)
                    return self.n_ctx
            except Exception:
                continue
        return 0

    async def ensure_context(self) -> int:
        if not self.n_ctx:
            await self.detect_context()
        if not self.n_ctx:
            self.n_ctx = config.CONTEXT_FALLBACK_TOKENS
        return self.n_ctx

    def char_budget(self, max_tokens: int | None = None) -> int:
        """Сколько символов промпта безопасно при данном контексте и длине ответа."""
        tokens = max_tokens or config.MAX_ANSWER_TOKENS
        ctx = self.n_ctx or config.CONTEXT_FALLBACK_TOKENS
        usable = max(512, ctx - tokens - config.TOKEN_RESERVE)
        return int(min(config.PROMPT_CHAR_BUDGET, usable * config.CHARS_PER_TOKEN))

    # ------------------------------------------------------------------ промпт
    def build_messages(self, question: str, context: str = "", history: list[dict] | None = None,
                       lang: str = "ru", max_tokens: int | None = None,
                       digest: str = "") -> list[dict]:
        """Контекст идёт в ПОСЛЕДНЕЕ сообщение пользователя, system остаётся неизменным.

        Так префикс промпта стабилен и llama-server переиспользует кэш промпта — это
        заметно ускоряет повторные вопросы на слабом CPU.
        """
        system = base_system_prompt(lang)
        # Сегодняшняя дата, день недели, номер недели — модель этого не знает сама.
        system += "\n\n" + clock.facts(lang)
        if digest:
            system += "\n\n" + digest
        budget = self.char_budget(max_tokens)

        if context:
            room = max(400, budget - len(system) - len(question) - 200)
            user_content = ("ФРАГМЕНТЫ ДОКУМЕНТАЦИИ (отвечай только по ним):\n"
                            + context[:room] + "\n\n---\nВОПРОС: " + question)
        else:
            user_content = question

        messages: list[dict] = [{"role": "system", "content": system}]
        left = budget - len(system) - len(user_content)
        chosen: list[dict] = []
        for msg in reversed(list(history or [])[-2 * config.MAX_HISTORY_TURNS:]):
            size = len(msg.get("content", ""))
            if left - size < 0:
                break
            left -= size
            chosen.append(msg)
        messages.extend(reversed(chosen))
        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def _shrink(messages: list[dict]) -> list[dict]:
        """Аварийное урезание: инструкции оставляем, контекст и историю режем."""
        out: list[dict] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                text = msg.get("content", "")
                out.append({"role": "system", "content": text[: max(600, len(text) // 2)]})
            elif i == len(messages) - 1:
                out.append(msg)
        return out

    # ------------------------------------------------------------------ генерация
    async def stream_chat(self, messages: list[dict], on_delta: DeltaCB | None = None,
                          cancel: asyncio.Event | None = None, max_tokens: int | None = None,
                          allow_retry: bool = True) -> str:
        """Стримит ответ. При переполнении контекста один раз повторяет с урезанным промптом."""
        tokens = max_tokens or config.MAX_ANSWER_TOKENS
        payload: dict = {
            "messages": messages,
            "stream": True,
            "temperature": config.TEMPERATURE,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "max_tokens": tokens,
            "cache_prompt": True,
        }
        if config.DISABLE_THINKING:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        answer: list[str] = []
        try:
            async with self.client.stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "ignore")
                    raise RuntimeError(_short_error(resp.status_code, body))
                async for line in resp.aiter_lines():
                    if cancel is not None and cancel.is_set():
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_delta(chunk)
                    if not text:
                        continue
                    answer.append(text)
                    if on_delta is not None:
                        await on_delta(text)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise RuntimeError(f"связь с llama-server потеряна: {exc}") from exc
        except RuntimeError as exc:
            if allow_retry and _is_context_error(str(exc)):
                self.shrunk = True
                smaller = self._shrink(messages)
                self.n_ctx = max(1024, int(self.n_ctx * 0.6))
                return await self.stream_chat(smaller, on_delta, cancel,
                                              max(96, tokens // 2), allow_retry=False)
            raise
        self.last_error = ""
        return "".join(answer)

    async def complete(self, messages: list[dict], max_tokens: int | None = None) -> str:
        """Без стриминга (запасной вариант)."""
        payload = {
            "messages": messages,
            "stream": False,
            "temperature": config.TEMPERATURE,
            "max_tokens": max_tokens or config.MAX_ANSWER_TOKENS,
        }
        resp = await self.client.post(f"{self.base_url}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


def _short_error(status: int, body: str) -> str:
    """Короткое человеческое описание ошибки llama-server."""
    try:
        payload = json.loads(body)
        message = (payload.get("error") or {}).get("message") or payload.get("message") or ""
    except json.JSONDecodeError:
        message = body.strip()
    message = " ".join(str(message).split())
    if len(message) > 220:
        message = message[:220] + "…"
    return f"llama-server ответил {status}: {message}"


def _is_context_error(text: str) -> bool:
    low = text.lower()
    return "context" in low or "exceed" in low or "too large" in low


def _extract_delta(chunk: dict) -> str:
    """Кусочек текста из SSE-чанка (поддерживает разные форматы llama-server)."""
    choices = chunk.get("choices") or []
    if not choices:
        return chunk.get("content") or ""
    choice = choices[0]
    delta = choice.get("delta")
    if isinstance(delta, dict):
        return delta.get("content") or ""
    message = choice.get("message")
    if isinstance(message, dict):
        return message.get("content") or ""
    return choice.get("text") or chunk.get("content") or ""
