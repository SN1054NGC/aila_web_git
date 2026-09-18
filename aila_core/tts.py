# -*- coding: utf-8 -*-
"""Синтез речи офлайн: Silero (torch) или Piper (ONNX). Оба варианта — локальные файлы.

Схема работы:
  текст -> нормализация (числа/аббревиатуры) -> ударения -> предложения ->
  синтез каждого предложения -> WAV с паузой по знаку препинания.

Никаких обращений в сеть: модели берутся только из локального каталога models/.
"""
from __future__ import annotations

import io
import os
import shutil
import threading
import time
import wave
from pathlib import Path
from typing import Any

from . import accents as accents_mod
from . import config
from . import textnorm

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def silence(ms: int, sample_rate: int) -> bytes:
    if ms <= 0:
        return b""
    return b"\x00\x00" * int(sample_rate * ms / 1000)


def _float_to_pcm16(audio: Any, normalize: bool = True) -> bytes:
    """torch.Tensor/ndarray -> int16 PCM.

    Нормализация по пику — как в старых исходниках (max(abs) -> 32767):
    без неё Silero звучит тихо и неровно между фрагментами.
    """
    if np is None:
        raise RuntimeError("numpy недоступен")
    arr = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    arr = np.asarray(arr, dtype=np.float32).reshape(-1)
    if not arr.size:
        return b""
    peak = float(np.max(np.abs(arr)))
    if normalize and peak > 0.01:
        arr = arr / peak
    return (np.clip(arr, -1.0, 1.0) * 32767).astype("<i2").tobytes()


class BaseEngine:
    name = "none"
    marker = "+"          # как движок помечает ударный гласный

    def __init__(self) -> None:
        self.ready = False
        self.error = ""
        self.sample_rate = 24000
        self._lock = threading.Lock()

    def load(self) -> bool:
        raise NotImplementedError

    def _synth(self, text: str, lang: str, voice: str | None = None) -> bytes:
        raise NotImplementedError

    def synth(self, text: str, lang: str, voice: str | None = None) -> bytes:
        with self._lock:                      # синтез не потокобезопасен
            return self._synth(text, lang, voice)

    def supports(self, lang: str) -> bool:
        """Есть ли голос для этого языка (смешанный текст читаем двумя голосами)."""
        return True

    def voices(self, lang: str) -> list[tuple[str, str]]:
        """[(id голоса, подпись)] — для выбора в интерфейсе."""
        return []


class SileroEngine(BaseEngine):
    """Silero TTS — тот же путь загрузки, что в старых рабочих исходниках:

        self.tts, _ = torch.hub.load('snakers4/silero-models', 'silero_tts',
                                     language='ru', speaker='v3_1_ru', trust_repo=True)
        audio = self.tts.apply_tts(text=..., speaker='baya', sample_rate=24000)

    Порядок попыток (первая успешная выигрывает):
      1) torch.hub.load        — как в оригинале (интернет нужен один раз, потом кэш);
      2) torch.hub.load_local  — офлайн по копии репозитория models/silero/repo;
      3) torch.package         — офлайн только по .pt-файлу (крайний случай).
    """

    name = "silero"
    marker = "+"

    # ВАЖНО: put_accent=True у Silero означает «уважать знаки + в тексте»,
    # поэтому наш словарь ударений работает так же, как в старом коде.
    # v3_1_ru — модель первой версии, поэтому её файл ищем первым.
    FILES = {"ru": ["v3_1_ru.pt", "model_ru.pt", "v4_ru.pt"],
             "en": ["v3_en.pt", "model_en.pt", "v4_en.pt"]}

    def __init__(self) -> None:
        super().__init__()
        self._models: dict[str, Any] = {}
        self.voice_of: dict[str, str] = {}
        self.loaded_via: dict[str, str] = {}

    # ---------------------------------------------------------------- пути
    def _candidate_files(self, lang: str) -> list[Path]:
        out: list[Path] = [config.SILERO_DIR / name for name in self.FILES.get(lang, [])]
        if config.SILERO_DIR.exists():
            out.extend(sorted(config.SILERO_DIR.glob(f"*{lang}*.pt")))
        seen: set[Path] = set()
        result: list[Path] = []
        for path in out:
            if not path.exists() or path in seen:
                continue
            seen.add(path)
            # Недокачанный файл бесполезен: рядом лежит .chunk или размер слишком мал
            if path.with_suffix(path.suffix + ".chunk").exists():
                continue
            if path.stat().st_size < 5 * 1024 * 1024:
                continue
            result.append(path)
        return result

    def _file_for_family(self, family: str, files: list[Path]) -> Path | None:
        """Подобрать .pt-файл под семейство голоса: v3_1_ru -> v3_1_ru.pt, v4_ru -> v4_ru.pt."""
        tag = family.split("_")[0].lower()          # 'v3' или 'v4'
        for path in files:
            if tag in path.name.lower():
                return path
        for path in files:
            if path.name.lower().startswith("model"):
                return path
        return files[0] if files else None

    def _families(self, lang: str) -> list[tuple[str, str]]:
        """[(семейство для hubconf, голос для apply_tts)] — как 'v3_1_ru' + 'baya'."""
        out: list[tuple[str, str]] = []
        for item in config.SILERO_SPEAKERS.get(lang, []):
            family, _, voice = item.partition(":")
            out.append((family, voice or "baya"))
        if not out:
            out.append(("v3_1_ru" if lang == "ru" else "v3_en", "baya" if lang == "ru" else "en_21"))
        return out

    def _seed_hub_checkpoints(self) -> None:
        """hubconf ищет .pt в кэше torch — положим их туда заранее (офлайн-режим)."""
        try:
            import torch
            hub_dir = Path(torch.hub.get_dir()) / "checkpoints"
            hub_dir.mkdir(parents=True, exist_ok=True)
            for pt in config.SILERO_DIR.glob("*.pt"):
                target = hub_dir / pt.name
                if not target.exists():
                    shutil.copy2(pt, target)
        except Exception:
            pass

    # ---------------------------------------------------------------- загрузка
    def _via_hub(self, lang: str, family: str, local: bool) -> Any:
        import torch
        if local:
            repo = config.SILERO_DIR / "repo"
            if not (repo / "hubconf.py").exists():
                raise RuntimeError("нет локальной копии silero-models (models/silero/repo)")
            # torch.hub.load_local в torch 2.x отсутствует — локальный репозиторий
            # подключается через source="local"
            return torch.hub.load(str(repo), "silero_tts", source="local",
                                  language=lang, speaker=family, trust_repo=True)[0]
        return torch.hub.load("snakers4/silero-models", "silero_tts",
                              language=lang, speaker=family, trust_repo=True)[0]

    def _via_package(self, path: Path) -> Any:
        import torch
        return torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")

    def _load_model(self, lang: str) -> Any:
        import torch
        torch.set_num_threads(max(1, (os.cpu_count() or 4) // 2))
        files = self._candidate_files(lang)
        problems: list[str] = []
        for family, voice in self._families(lang):
            # 1) локальный .pt — мгновенно и полностью офлайн (так работает после первой загрузки)
            local_file = self._file_for_family(family, files)
            if local_file is not None:
                try:
                    model = self._via_package(local_file)
                    self._models[lang] = model
                    self.voice_of[lang] = voice
                    self.loaded_via[lang] = f"package:{local_file.name}"
                    return model
                except Exception as exc:
                    problems.append(f"package:{local_file.name}: {type(exc).__name__}")
            # 2) torch.hub — тот же путь, что в первой версии (скачает модель при необходимости)
            for mode, local in (("local", True), ("hub", False)):
                try:
                    model = self._via_hub(lang, family, local)
                    self._models[lang] = model
                    self.voice_of[lang] = voice
                    self.loaded_via[lang] = f"{mode}:{family}"
                    return model
                except Exception as exc:
                    problems.append(f"{mode}/{family}: {type(exc).__name__}: {str(exc)[:60]}")
        raise RuntimeError(
            f"Silero '{lang}' не загрузился ({', '.join(problems) or 'нет файлов'}). "
            "Проверьте models/silero (tools/fetch_models.py --only silero) и интернет для torch.hub.")

    def load(self) -> bool:
        try:
            import torch  # noqa: F401
        except Exception as exc:
            self.error = f"torch недоступен: {exc}"
            return False
        self._seed_hub_checkpoints()
        if not any(self._candidate_files(lang) for lang in ("ru", "en")):
            self.error = (f"нет .pt-моделей в {config.SILERO_DIR} "
                          "(см. tools/fetch_models.py --only silero)")
            return False
        self.error = ""
        self.ready = True
        return True

    # ---------------------------------------------------------------- синтез
    def supports(self, lang: str) -> bool:
        return bool(self._candidate_files(lang))

    def voices(self, lang: str) -> list[tuple[str, str]]:
        return [(name, f"Silero {name}") for name in config.SILERO_VOICES.get(lang, [])]

    def _synth(self, text: str, lang: str, voice: str | None = None) -> bytes:
        model = self._models.get(lang) or self._load_model(lang)
        speaker = voice or self.voice_of.get(lang) or self._families(lang)[0][1]
        last: Exception | None = None
        preferred = config.SILERO_SAMPLE_RATE
        rates = [preferred] + [r for r in (48000, 24000, 8000) if r != preferred]
        for rate in rates:
            # 1) сигнатура как в старом коде
            try:
                audio = model.apply_tts(text=text, speaker=speaker, sample_rate=rate)  # type: ignore[attr-defined]
                self.sample_rate = rate
                return _float_to_pcm16(audio, normalize=True)
            except TypeError as exc:
                last = exc
            except Exception as exc:
                last = exc
            # 2) с явными флагами ударений/ё (v4)
            try:
                audio = model.apply_tts(text=text, speaker=speaker, sample_rate=rate,  # type: ignore[attr-defined]
                                        put_accent=True, put_yo=True)
                self.sample_rate = rate
                return _float_to_pcm16(audio, normalize=True)
            except Exception as exc:
                last = exc
        raise RuntimeError(f"Silero не смог синтезировать текст: {last}")


class PiperEngine(BaseEngine):
    """Piper: быстрый ONNX-синтез, отлично живёт на слабом CPU (torch не нужен)."""

    name = "piper"
    marker = "'"          # espeak-ng помечает ударение апострофом

    def __init__(self) -> None:
        super().__init__()
        self._voices: dict[str, object] = {}

    def load(self) -> bool:
        try:
            import piper  # noqa: F401
        except Exception as exc:
            self.error = f"пакет piper-tts недоступен: {exc}"
            return False
        found = [lang for lang in ("ru", "en") if config.piper_voice_path(lang)]
        if not found:
            self.error = (f"нет голосов Piper в {config.PIPER_DIR} "
                          "(см. tools/fetch_models.py)")
            return False
        self.error = ""
        self.ready = True
        return True

    def supports(self, lang: str) -> bool:
        return config.piper_voice_path(lang) is not None

    def voices(self, lang: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for name in config.PIPER_VOICES.get(lang, []):
            if config.piper_voice_path(lang, name):
                out.append((name, f"Piper {name}"))
        return out

    def _voice(self, lang: str, voice: str | None = None) -> Any:
        key = f"{lang}:{voice or ''}"
        if key in self._voices:
            return self._voices[key]
        from piper import PiperVoice
        found = config.piper_voice_path(lang, voice)
        if not found:
            raise RuntimeError(f"нет голоса Piper для '{lang}'")
        onnx_path, cfg_path = found
        loaded = PiperVoice.load(str(onnx_path), config_path=str(cfg_path))
        self._voices[key] = loaded
        return loaded

    def _synth(self, text: str, lang: str, voice_name: str | None = None) -> bytes:
        """Поддержаны все версии piper: 1.3+ (synthesize), 1.2 (stream_raw) и synthesize_wav."""
        voice = self._voice(lang, voice_name)
        default_rate = int(getattr(getattr(voice, "config", None), "sample_rate", 22050) or 22050)

        # 1) piper >= 1.3: synthesize() отдаёт готовые PCM-куски (AudioChunk)
        synthesize = getattr(voice, "synthesize", None)
        if callable(synthesize):
            try:
                buffer_pcm = bytearray()
                rate = default_rate
                for chunk in synthesize(text):
                    data = getattr(chunk, "audio_int16_bytes", None)
                    if data is None and isinstance(chunk, (bytes, bytearray)):
                        data = bytes(chunk)
                    if data:
                        buffer_pcm.extend(data)
                    rate = int(getattr(chunk, "sample_rate", rate) or rate)
                if buffer_pcm:
                    self.sample_rate = rate
                    return bytes(buffer_pcm)
            except Exception as exc:
                self.error = f"synthesize: {exc}"

        # 2) piper 1.2: синтез сырым потоком
        stream_raw = getattr(voice, "synthesize_stream_raw", None)
        if callable(stream_raw):
            try:
                joined = b"".join(raw if isinstance(raw, bytes) else bytes(raw)
                                  for raw in stream_raw(text))
                if joined:
                    self.sample_rate = default_rate
                    return joined
            except Exception as exc:
                self.error = f"stream_raw: {exc}"

        # 3) универсальный вариант: пишем WAV в буфер
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(text, wav)  # type: ignore[attr-defined]
        buffer.seek(0)
        with wave.open(buffer, "rb") as reader:
            self.sample_rate = reader.getframerate()
            return reader.readframes(reader.getnframes())


class TTSService:
    """Готовый сервис: выбирает движок, нормализует текст, режет на фрагменты."""

    def __init__(self) -> None:
        self.engine: BaseEngine = BaseEngine()
        self.dictionary = accents_mod.load_default(config.DATA_DIR / "accent_dict.json")
        self.error = ""
        self._loaded = False
        self._lock = threading.Lock()
        self._last_attempt = 0.0
        self._retrying = False
        self.auto_retry = True          # подхватить модели, если их скачали позже

    def _models_present(self) -> bool:
        if config.piper_voice_path("ru") or config.piper_voice_path("en"):
            return True
        for lang in ("ru", "en"):
            for name in SileroEngine.FILES.get(lang, []):
                if (config.SILERO_DIR / name).exists():
                    return True
        return False

    def _retry_async(self) -> None:
        """Фоновая повторная попытка загрузки: модели могли появиться после старта."""
        if self._retrying:
            return
        self._retrying = True

        def worker() -> None:
            try:
                with self._lock:
                    self._loaded = False
                self.load()
            finally:
                self._retrying = False

        threading.Thread(target=worker, name="aila-tts-retry", daemon=True).start()

    # ------------------------------------------------------------------ загрузка
    def load(self) -> bool:
        with self._lock:
            if self._loaded:
                return self.engine.ready
            self._loaded = True
            self._last_attempt = time.monotonic()
            # Первая версия проекта использовала Silero — он и основной, Piper запасной.
            wanted = config.TTS_ENGINE
            order = {"silero": ["silero", "piper"], "auto": ["silero", "piper"],
                     "piper": ["piper", "silero"], "none": []}.get(wanted, ["silero", "piper"])
            for name in order:
                engine: BaseEngine = SileroEngine() if name == "silero" else PiperEngine()
                if engine.load():
                    self.engine = engine
                    self.error = ""
                    return True
                self.error = engine.error or self.error
            self.engine = BaseEngine()
            return False

    @property
    def ready(self) -> bool:
        return self.engine.ready

    def status(self) -> dict:
        # если модели появились после старта — подхватываем сами, раз в 20 секунд
        if (self.auto_retry and not self.ready and self._models_present()
                and time.monotonic() - self._last_attempt > 20):
            self._retry_async()
        return {
            "ready": self.ready,
            "engine": self.engine.name,
            "sample_rate": self.engine.sample_rate,
            "marker": self.engine.marker,
            "accents": len(self.dictionary),
            "via": getattr(self.engine, "loaded_via", {}),
            "error": self.error if not self.ready else self.engine.error,
        }

    # ------------------------------------------------------------------ синтез
    def available_voices(self) -> dict:
        """Список голосов текущего движка — для выпадающего списка в интерфейсе."""
        if not self.ready:
            return {"engine": self.engine.name, "ru": [], "en": []}
        return {
            "engine": self.engine.name,
            "ru": [{"id": i, "label": label} for i, label in self.engine.voices("ru")],
            "en": [{"id": i, "label": label} for i, label in self.engine.voices("en")],
        }

    def prepare_text(self, text: str, lang: str = "auto") -> str:
        if lang == "auto":
            lang = textnorm.detect_lang(text)
        normalized = textnorm.normalize_for_speech(text, lang)
        if lang == "ru":
            normalized = accents_mod.apply_accents(normalized, self.dictionary, self.engine.marker)
        return normalized

    def chunks(self, text: str, lang: str = "auto", pause_scale: float = 1.0,
               voice: str | None = None) -> list[dict]:
        """Готовые фрагменты для отправки в браузер: WAV + пауза после него.

        Язык определяется по КАЖДОМУ предложению: английские вставки в русском ответе
        читаются английским голосом, и наоборот — иначе латиница звучит «по-русски».
        """
        if not self.ready:
            return []
        base_lang = lang if lang in ("ru", "en") else textnorm.detect_lang(text)
        # Заводские номера вслух не читаем: вместо них одна пометка «…— в чате»
        text = textnorm.replace_serials_once(text)
        sentences = textnorm.split_sentences(text, config.TTS_MAX_CHUNK, merge=False)

        # Группируем соседние предложения одного языка: русские читает русский голос,
        # английские вставки — английский.
        groups: list[tuple[str, list[str]]] = []
        for sentence in sentences:
            sentence_lang = base_lang
            if lang == "auto":
                sentence_lang = textnorm.detect_lang(sentence, base_lang)
            if not self.engine.supports(sentence_lang):
                sentence_lang = base_lang
            if (groups and groups[-1][0] == sentence_lang
                    and len(" ".join(groups[-1][1])) + len(sentence) + 1 <= config.TTS_MAX_CHUNK):
                groups[-1][1].append(sentence)
            else:
                groups.append((sentence_lang, [sentence]))

        out: list[dict] = []
        for index, (part_lang, sentences_of_lang) in enumerate(groups):
            prepared = self.prepare_text(" ".join(sentences_of_lang), part_lang)
            try:
                pcm = self.engine.synth(prepared, part_lang, voice)
            except Exception as exc:
                self.error = str(exc)
                break
            if not pcm:
                continue
            tail = int(config.TTS_SILENCE_MS.get(prepared[-1:], 150)
                       * max(0.1, min(3.0, pause_scale)))
            if index == len(groups) - 1:
                tail = 120
            pcm += silence(tail, self.engine.sample_rate)
            out.append({
                "index": index,
                "wav": pcm_to_wav(pcm, self.engine.sample_rate),
                "text": prepared,
                "lang": part_lang,
            })
        return out


if __name__ == "__main__":
    service = TTSService()
    print("tts:", service.status())
    demo = "Привет! Я Айла. Код 3 — это преобразователь расхода, ТО-3 проводится двенадцатого числа."
    print("normalized:", service.prepare_text(demo, "ru"))
