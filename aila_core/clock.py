# -*- coding: utf-8 -*-
"""Текущая дата и время: факты для модели и точные ответы на «какое сегодня число».

Зачем модуль:
  * локальная модель не знает, какой сегодня день, — факты подкладываются в системный промпт;
  * ответ про дату не должен ждать генерации на CPU (это десятки секунд) — на такие вопросы
    отвечаем мгновенно и точно, без выдумывания.

Все формы — и для показа (цифрами), и для речи (словами с правильными окончаниями).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import textnorm

WEEKDAYS_RU = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS_RU_NOM = ("", "январь", "февраль", "март", "апрель", "май", "июнь",
                 "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
MONTHS_EN = ("", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December")

# Какие бывают вопросы о календаре
_KINDS: list[tuple[str, str]] = [
    (r"како[ей]\s+(сегодня|сейчас)\s+(число|дата|день)\b", "full"),
    (r"\bсегодняшн(яя|ее)\s+(дата|число)\b", "full"),
    (r"какое\s+(сегодня\s+)?число\b", "full"),
    (r"какой\s+(сегодня\s+)?день\s+недели\b", "weekday"),
    (r"как(ая|ой)\s+(сейчас\s+|ид[её]т\s+)?недел", "week"),
    (r"(номер|какая)\s+недели\b", "week"),
    (r"как(ой|ая)\s+(сейчас\s+)?месяц\b", "month"),
    (r"как(ой|ая)\s+(сейчас\s+)?год\b", "year"),
    (r"какой\s+(сейчас\s+)?квартал\b", "quarter"),
    (r"(который\s+час|сколько\s+(сейчас\s+)?времени|текущее\s+время)", "time"),
    (r"какое\s+число\s+(было\s+)?вчера|какой\s+(день\s+)?(был\s+)?вчера", "yesterday"),
    (r"какое\s+число\s+(будет\s+)?завтра|какой\s+(день\s+)?(будет\s+)?завтра", "tomorrow"),
    (r"what('s| is)? (the )?(date|day)( today)?\b", "full"),
    (r"what day is it\b", "weekday"),
    (r"what (week|month|year|time) is it\b", "week"),
]


def today(now: datetime | None = None) -> datetime:
    return now or datetime.now()


def weekday_ru(dt: datetime) -> str:
    return WEEKDAYS_RU[dt.weekday()]


def weekday_en(dt: datetime) -> str:
    return WEEKDAYS_EN[dt.weekday()]


def week_of_month(dt: datetime) -> int:
    """Какая по счёту неделя месяца (1..5) — по календарным семёркам."""
    return (dt.day - 1) // 7 + 1


def iso_week(dt: datetime) -> int:
    """Номер недели по ISO 8601 (та самая «неделя по счёту»)."""
    return dt.isocalendar()[1]


def date_display(dt: datetime, lang: str = "ru") -> str:
    """Дата цифрами — для чата и документов."""
    if lang == "en":
        return f"{dt.day} {MONTHS_EN[dt.month]} {dt.year}"
    return f"{dt.day} {textnorm._RU_MONTHS_GEN[dt.month]} {dt.year} года"


def date_speech(dt: datetime, lang: str = "ru") -> str:
    """Дата словами с правильными окончаниями — для озвучки."""
    if lang == "en":
        return (f"{textnorm.ordinal_en(dt.day)} of {MONTHS_EN[dt.month]} {dt.year}")
    return (f"{textnorm.ordinal_ru(dt.day, 'n')} "
            f"{textnorm._RU_MONTHS_GEN[dt.month]} "
            f"{textnorm.year_ru_genitive(dt.year)} года")


def facts(lang: str = "ru", now: datetime | None = None) -> str:
    """Компактная сводка о «сейчас» — идёт в системный промпт модели."""
    dt = today(now)
    yesterday = dt - timedelta(days=1)
    tomorrow = dt + timedelta(days=1)
    if lang == "en":
        return (f"NOW: {weekday_en(dt)}, {date_display(dt, 'en')}, {dt:%H:%M} (local time). "
                f"ISO week: {iso_week(dt)}. Week of month: {week_of_month(dt)}. "
                f"Day of year: {dt.timetuple().tm_yday}. Quarter: {(dt.month - 1) // 3 + 1}. "
                f"Yesterday: {date_display(yesterday, 'en')}, tomorrow: {date_display(tomorrow, 'en')}. "
                "Use these facts for any question about today's date, day, week, month or year.")
    return (f"СЕЙЧАС: {weekday_ru(dt)}, {date_display(dt, 'ru')}, {dt:%H:%M} (местное время). "
            f"Неделя: {iso_week(dt)}-я по ISO, {week_of_month(dt)}-я неделя "
            f"{textnorm._RU_MONTHS_GEN[dt.month]}. "
            f"День года: {dt.timetuple().tm_yday}. Квартал: {(dt.month - 1) // 3 + 1}. "
            f"Вчера: {date_display(yesterday, 'ru')}, завтра: {date_display(tomorrow, 'ru')}. "
            "Для любых вопросов о сегодняшней дате, дне недели, неделе, месяце и годе используй эти данные.")


def _build(kind: str, dt: datetime, lang: str) -> str:
    yesterday = dt - timedelta(days=1)
    tomorrow = dt + timedelta(days=1)
    if lang == "en":
        mapping = {
            "full": f"Today is {weekday_en(dt)}, {date_display(dt, 'en')}.",
            "weekday": f"Today is {weekday_en(dt)}.",
            "week": (f"We are in ISO week {iso_week(dt)} of {dt.year} "
                     f"(week {week_of_month(dt)} of {MONTHS_EN[dt.month]})."),
            "month": f"It is {MONTHS_EN[dt.month]} {dt.year}.",
            "year": f"It is {dt.year}.",
            "quarter": f"Quarter {(dt.month - 1) // 3 + 1} of {dt.year}.",
            "time": f"It is {dt.hour}:{dt.minute:02d}.",
            "yesterday": f"Yesterday was {weekday_en(yesterday)}, {date_display(yesterday, 'en')}.",
            "tomorrow": f"Tomorrow is {weekday_en(tomorrow)}, {date_display(tomorrow, 'en')}.",
        }
        return mapping.get(kind, "")
    month_gen = textnorm._RU_MONTHS_GEN[dt.month]
    mapping = {
        "full": f"Сегодня {weekday_ru(dt)}, {date_display(dt)}.",
        "weekday": f"Сегодня {weekday_ru(dt)}.",
        "week": (f"Идёт {iso_week(dt)}-я неделя года по ISO, "
                 f"это {week_of_month(dt)}-я неделя {month_gen}."),
        "month": f"Сейчас {MONTHS_RU_NOM[dt.month]} {dt.year} года.",
        "year": f"Сейчас {dt.year} год.",
        "quarter": f"Идёт {(dt.month - 1) // 3 + 1}-й квартал {dt.year} года.",
        "time": f"Сейчас {dt.hour}:{dt.minute:02d}.",
        "yesterday": f"Вчера было {weekday_ru(yesterday)}, {date_display(yesterday)}.",
        "tomorrow": f"Завтра будет {weekday_ru(tomorrow)}, {date_display(tomorrow)}.",
    }
    return mapping.get(kind, "")


# Слова, по которым видно, что вопрос про ДОКУМЕНТ, а не про сегодняшнюю дату:
# «какой год у графика» — это не «какой сейчас год», тут отвечает модель по документу.
_DOCUMENT_MARKERS = ("документ", "график", "файл", "таблиц", "токмх", "to kmh", "кмх",
                     "лист", "составлен", "по плану", "в плане", "в книге", "excel")


def kind_of(question: str) -> str | None:
    """Определяет, спрашивают ли про календарь. Возвращает вид вопроса или None."""
    low = (question or "").lower().replace("ё", "е")
    if any(marker in low for marker in _DOCUMENT_MARKERS):
        return None
    for pattern, kind in _KINDS:
        if re.search(pattern, low):
            return kind
    return None


def answer(question: str, lang: str = "ru", now: datetime | None = None) -> str | None:
    """Готовый точный ответ на календарный вопрос (или None, если вопрос не об этом)."""
    kind = kind_of(question)
    if not kind:
        return None
    return _build(kind, today(now), lang)


if __name__ == "__main__":
    dt = today()
    print("факты:", facts(now=dt))
    for q in ["какое сегодня число", "какой сегодня день недели", "какая неделя по счету",
              "какой сейчас месяц", "какой год", "который час", "какое число было вчера",
              "какое число будет завтра", "какой квартал",
              "какой год у графика в документе", "какой месяц в файле",
              "какое оборудование под кодом 3"]:
        print(f"  {q!r:45} -> {answer(q, now=dt)!r}")
