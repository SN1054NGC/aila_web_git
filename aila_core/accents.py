# -*- coding: utf-8 -*-
"""Расстановка ударений для русского TTS.

Словарь — это СЛОЙ ПЕРЕОПРЕДЕЛЕНИЙ для слов, которые синтезатор читает неправильно
(термины, аббревиатуры, названия). Базовое ударение ставит сам движок синтеза.

Исправлено по сравнению со старой версией:
  * регистр исходного слова сохраняется ("Работа" -> "Раб+ота", а не "раб+ота");
  * падежные формы ищутся через лёгкую нормализацию основы;
  * слова, где ударение уже стоит, не трогаются;
  * маркер ударения настраивается под движок: Silero -> "+", espeak/Piper -> "'".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_MARKER = "+"

# Хвосты, отбрасываемые при поиске основы (падеж/число/род).
_ENDINGS = (
    # 4 буквы — раньше коротких, иначе «-иями» перехватит «-ями»
    "иями",
    # 3 буквы
    "ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "иях", "иям", "ией",
    # 2 буквы (в том числе родительный/дательный слов на «-ия»: «-ии»)
    "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей", "ый", "ий", "ом", "ем", "ам", "ям",
    "ах", "ях", "ов", "ев", "ью", "ию", "ия", "ии", "ую", "юю",
    # 1 буква
    "а", "я", "о", "е", "у", "ю", "ы", "и", "ь", "й",
)


def _norm_key(word: str) -> str:
    w = word.lower().replace("ё", "е")
    for end in _ENDINGS:
        if len(w) - len(end) >= 4 and w.endswith(end):
            return w[: -len(end)]
    return w


_VOWELS = "аеёиоуыэюя"

_MARKERS = ("+", "'")


def _stress_index(accented: str) -> tuple[str, int] | None:
    """Каким знаком помечено ударение и на каком месте стоит ударный гласный."""
    for marker in _MARKERS:
        if marker in accented:
            return marker, accented.index(marker)
    return None


def _transfer_stress(source: str, accented: str) -> str | None:
    """Перенести позицию ударения из словарной формы в исходное слово.

    «пов'ерка» + «поверке» -> «пов'ерке». Если на том месте не гласная —
    возвращаем None, чтобы не испортить слово.
    """
    found = _stress_index(accented)
    if not found:
        return None
    marker, index = found
    if index >= len(source) or source[index].lower() not in _VOWELS:
        return None
    return source[:index] + marker + source[index:]


def _match_case(source: str, accented: str) -> str:
    if not accented:
        return accented
    if source.isupper() and len(source) > 1:
        return accented.upper()
    if source[:1].isupper():
        return accented[:1].upper() + accented[1:]
    return accented


class AccentDictionary:
    """Словарь ударений вида {слово: сл+ово}."""

    def __init__(self, entries: dict[str, str] | None = None, path: Path | None = None,
                 keep_marker: str = DEFAULT_MARKER) -> None:
        self.raw: dict[str, str] = {}
        self.by_norm: dict[str, str] = {}
        self.keep_marker = keep_marker
        self.path = Path(path) if path else None
        if path and Path(path).exists():
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.raw = {str(k): str(v) for k, v in data.items() if k and v}
            except Exception:
                self.raw = {}
        if entries:
            for key, value in entries.items():
                self.raw.setdefault(key, value)
        for key, value in self.raw.items():
            self.by_norm[_norm_key(key)] = value
        # Словосочетания обрабатываем отдельно и длинные — раньше коротких
        # (так же, как в tam_001/tts_engine.py).
        self._rebuild_phrases()

    def _rebuild_phrases(self) -> None:
        self.phrases = sorted((k for k in self.raw if " " in k), key=len, reverse=True)

    def add(self, word: str, accented: str) -> None:
        """Добавить или исправить ударение во время работы."""
        word = (word or "").strip()
        accented = (accented or "").strip()
        if not word or not accented:
            return
        self.raw[word.lower()] = accented
        self.by_norm[_norm_key(word)] = accented
        if " " in word:
            self._rebuild_phrases()

    def save(self, path: Path | None = None) -> bool:
        """Сохранить словарь на диск (чтобы правки ударений не терялись)."""
        target = Path(path) if path else self.path
        if target is None:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            ordered = {k: self.raw[k] for k in sorted(self.raw)}
            target.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    def __len__(self) -> int:
        return len(self.raw)

    def lookup(self, word: str) -> tuple[str | None, bool]:
        """Возвращает (форма с ударением, точное ли совпадение).

        Точное совпадение — слово есть в словаре как есть. Иначе форма найдена по основе
        (падеж, число), и её нельзя подставлять целиком: изменилось бы окончание.
        """
        if not word or "+" in word or "'" in word:
            return None, False
        low = word.lower().replace("ё", "е")
        if low in self.raw:
            return self.raw[low], True
        norm = _norm_key(word)
        if norm in self.by_norm:
            return self.by_norm[norm], False
        for key, value in self.raw.items():
            if key.lower().replace("ё", "е") == low:
                return value, True
        return None, False

    def apply(self, text: str) -> str:
        """Расставляет ударения из словаря, сохраняя регистр исходного слова."""
        if not text or not self.raw:
            return text

        # 1) словосочетания («при этом», «государственная поверка») — длинные первыми
        for phrase in self.phrases:
            value = self.raw[phrase]

            def repl_phrase(m: re.Match[str], v: str = value) -> str:
                return _match_case(m.group(0), v)

            pattern = re.escape(phrase).replace(" ", r"\s+")
            text = re.sub(r"(?<![А-Яа-яЁё])" + pattern + r"(?![А-Яа-яЁё])",
                          repl_phrase, text, flags=re.IGNORECASE)

        # 2) отдельные слова
        def repl(m: re.Match) -> str:
            word = m.group(0)
            found, exact = self.lookup(word)
            if not found:
                return word
            if exact:
                return _match_case(word, found)
            # Слово найдено по основе: переносим только позицию ударения,
            # иначе падежная форма заменилась бы именительным падежом
            # («при поверке» -> «при пов'ерка» — так было бы неправильно).
            transferred = _transfer_stress(word, found)
            return transferred or word

        return re.sub(r"[А-Яа-яЁё][А-Яа-яЁё-]{2,}", repl, text)


# Готовый словарь по умолчанию (основа; данные из data/accent_dict.json добавляются сверху).
BUILTIN = {
    "сикн": "с+икэн",
    "оборудование": "оборуд+ование",
    "техническое": "техн+ическое",
    "обслуживание": "обслуж+ивание",
    "метрологический": "метролог+ический",
    "контроль": "контр+оль",
    "преобразователь": "преобразов+атель",
    "расход": "расх+од",
    "плотность": "пл+отность",
    "вязкость": "в+язкость",
    "влагомер": "влагом+ер",
    "датчик": "д+атчик",
    "давление": "давл+ение",
    "температура": "температ+ура",
    "задвижка": "задв+ижка",
    "шкаф": "шк+аф",
    "искробезопасный": "искробезоп+асный",
    "барьер": "барь+ер",
    "коммутатор": "коммут+атор",
    "контроллер": "контр+оллер",
    "привет": "пр+ивет",
    "здравствуйте": "здр+авствуйте",
    "спасибо": "спас+ибо",
    "пожалуйста": "пож+алуйста",
    "хорошо": "хорош+о",
    "модель": "мод+ель",
    "вопрос": "вопр+ос",
    "ответ": "отв+ет",
    "конечно": "кон+ечно",
    "компьютер": "компь+ютер",
    "интернет": "интерн+ет",
    "программа": "прогр+амма",
    "сервер": "серв+ер",
    "график": "гр+афик",
    "поверка": "пов+ерка",
    "калибровка": "калибр+овка",
    "погрешность": "погр+ешность",
    "измерение": "измер+ение",
    "нефть": "н+ефть",
    "нефтепродукт": "нефтепрод+укт",
    "резервуар": "резерву+ар",
    "насос": "нас+ос",
    "трубопровод": "трубопров+од",
    "арматура": "армат+ура",
    "монтаж": "монт+аж",
    "демонтаж": "демонт+аж",
    "эксплуатация": "эксплуат+ация",
    "неисправность": "неиспр+авность",
    "проверка": "пров+ерка",
    "регламент": "реглам+ент",
    "документация": "документ+ация",
}


def apply_accents(text: str, dictionary: AccentDictionary, marker: str = DEFAULT_MARKER) -> str:
    """Применить словарь; при необходимости заменить маркер ударения под движок."""
    result = dictionary.apply(text)
    if marker and marker != DEFAULT_MARKER:
        result = result.replace(DEFAULT_MARKER, marker)
    return result


def load_default(data_path: Path | None = None) -> AccentDictionary:
    return AccentDictionary(entries=BUILTIN, path=data_path)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent / "data" / "accent_dict.json"
    d = load_default(here if here.exists() else None)
    print("слов в словаре:", len(d), "| файл:", here.exists())
    for src in ["Работа выполнена", "работы по графику", "СИКН № 1", "модели оборудования",
                "Привет, Айла!", "уже зад+анное", "преобразователь расхода"]:
        print(" ", repr(src), "->", repr(d.apply(src)))
