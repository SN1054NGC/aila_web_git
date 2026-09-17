#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка произношения, окончаний и календаря — без микрофона и без модели.

    python tools/diag_text.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aila_core import clock, textnorm  # noqa: E402

CASES = [
    ("дата словами", "Сегодня 17 сентября 2001 года."),
    ("дата цифрами", "Приказ от 14.02.2001 № 1"),
    ("год сокращённо", "Отчёт за 2001 г."),
    ("день без года", "Проверка 1 мая"),
    ("единицы: 5+", "Давление 20 МПа и 5 кг, 22 мм"),
    ("единицы: 2-4", "Давление 2 МПа и 3 кг"),
    ("единицы: 1", "Давление 1 МПа, 21 кг, 11 мм"),
    ("дроби", "Погрешность 0,5 % при 6,3 МПа"),
    ("расход", "Объём 1234 м³/ч, плотность 850 кг/м³"),
    ("температура", "Температура 20 °C и 1 °C"),
    ("ТО", "ТО-1 (14) и ТО-3 (07) по графику"),
    ("латиница", "Преобразователь расхода, датчик давления"),
    ("аббревиатуры", "Шкаф ИВК СИКН № 1, БИК, ТПР, КМХ, АСН"),
    ("ГОСТ", "ГОСТ 8.611-2013, пункт 5.2"),
]

def main() -> int:
    print("=" * 78)
    print("ПРОИЗНОШЕНИЕ И ОКОНЧАНИЯ")
    print("=" * 78)
    for name, src in CASES:
        out = textnorm.normalize_for_speech(src, "ru")
        print(f"\n  {name}:")
        print(f"    вход : {src}")
        print(f"    речь : {out}")

    print()
    print("=" * 78)
    print("КАЛЕНДАРЬ")
    print("=" * 78)
    print("  факты для модели:")
    print("   ", clock.facts())
    print()
    questions = [
        "какое сегодня число", "какой сегодня день недели", "какая неделя по счету",
        "какой сейчас месяц", "какой год", "который час", "какое число было вчера",
        "какое число будет завтра", "какой квартал",
        "какое оборудование под кодом 3",
    ]
    for q in questions:
        a = clock.answer(q)
        if a:
            spoken = textnorm.normalize_for_speech(a, "ru")
            print(f"\n  {q}")
            print(f"    ответ : {a}")
            print(f"    вслух : {spoken}")
        else:
            print(f"\n  {q}\n    -> не календарный вопрос (уйдёт в модель)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
