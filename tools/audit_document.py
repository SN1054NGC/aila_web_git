# -*- coding: utf-8 -*-
"""Сверка разбора документа с исходным Excel: месяцы, колонки, дни, покрытие RAG.

Запуск:
    .venv_311\Scripts\python.exe tools\audit_document.py [путь.xlsx]

Проверяет, что RAG собрал ровно те строки, что есть в файле, что месяцы определены
по правильным колонкам, что дни/виды ТО разобраны верно и что поля не перепутаны.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math
import re

import pandas as pd

from aila_core import config, kmhto
from aila_core.rag import RagEngine, fill_merged, read_merged_values

MAX_EXAMPLES = 5


def raw_grid(path: Path) -> dict[str, tuple[list[list[Any]], list[int]]]:
    """Лист -> (строки, число своих значений в строке).

    Объединённые ячейки разнесены так же, как в парсере: иначе сверять нечего.
    """
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    merges = read_merged_values(path)
    out: dict[str, tuple[list[list[Any]], list[int]]] = {}
    for name, frame in sheets.items():
        rows = [[None if value is None or (isinstance(value, float) and math.isnan(value)) else value
                 for value in row] for row in frame.values.tolist()]
        header_rows, data_start = kmhto.find_header_block(rows)
        own = [sum(1 for value in row if cell_text(value)) for row in rows]
        fill_merged(rows, merges.get(str(name), {}), data_start)
        out[str(name)] = (rows, own)
    return out


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\n", " ").strip()


def month_columns(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    """Строка заголовков месяцев и {номер месяца: индекс колонки}."""
    best_row, best_hits, best_map = -1, 0, {}
    for idx, row in enumerate(rows[:12]):
        found: dict[str, int] = {}
        for col, value in enumerate(row):
            number = kmhto.month_index(cell_text(value))
            if number and str(number) not in found:
                found[str(number)] = col
        if len(found) > best_hits:
            best_row, best_hits, best_map = idx, len(found), found
    return best_row, best_map


def code_column(rows: list[list[Any]], month_row: int) -> int:
    """Колонка с кодом оборудования — по заголовку над строкой месяцев."""
    for row in rows[max(0, month_row - 3):month_row]:
        for col, value in enumerate(row):
            low = cell_text(value).lower()
            if "код" in low:
                return col
    return 1


def name_columns(rows: list[list[Any]], month_row: int) -> dict[str, int]:
    """Колонки «наименование» и «место установки» по заголовкам."""
    found: dict[str, int] = {}
    for row in rows[max(0, month_row - 3):month_row]:
        for col, value in enumerate(row):
            low = cell_text(value).lower().replace("\n", " ")
            if "наимен" in low and "equipment" not in found:
                found["equipment"] = col
            elif "место" in low and "place" not in found:
                found["place"] = col
    return found


def expected_rows(rows: list[list[Any]], month_row: int, months: dict[str, int],
                  code_col: int, own: list[int]) -> dict[int, dict[str, Any]]:
    """Ожидаемые строки данных: {номер строки Excel: {...}}."""
    expect: dict[int, dict[str, Any]] = {}
    for idx in range(month_row + 1, len(rows)):
        row = rows[idx]
        code = cell_text(row[code_col]) if code_col < len(row) else ""
        cells = {num: cell_text(row[col]) for num, col in months.items() if col < len(row)}
        if not re.sub(r"[пП]$", "", code).isdigit():
            continue
        if own[idx] == 0:
            continue                 # строка целиком из объединённых ячеек
        if not any(kmhto.parse_days(text) or kmhto.parse_work_items(text) for text in cells.values()):
            continue
        expect[idx + 1] = {"code": code, "cells": cells}
    return expect


def reference_check(rows: list[list[Any]], docs: list[dict[str, Any]], sheet: str,
                    merges: dict[tuple[int, int], Any], own: list[int]) -> int:
    """Сверка листа-справочника: покрытие строк и наличие годовых норм времени."""
    header_rows, data_start = kmhto.find_header_block(rows)
    width = max(len(row) for row in rows)
    heads: list[str] = []
    for col in range(width):
        parts = [cell_text(rows[i][col]) for i in header_rows if col < len(rows[i])]
        heads.append(" ".join(part for part in parts if part).strip())
    code_col = code_column(rows, data_start)
    year_cols = [col for col, head in enumerate(heads) if "годов" in head.lower()]
    expect: dict[int, list[str]] = {}
    without_code = 0
    for index in range(data_start, len(rows)):
        cells = [cell_text(value) for value in rows[index]]
        if sum(1 for value in cells if value) < 2:
            continue
        if own[index] == 0:
            continue                 # строка целиком из объединённых ячеек
        if not cells[code_col]:
            without_code += 1
        expect[index + 1] = [cells[col] for col in year_cols if col < len(cells)]
    got = {int(d["meta"]["row"]): d for d in docs if str(d["meta"].get("sheet")) == sheet}
    print(f"\n[{sheet}] роль: {kmhto.sheet_role(sheet)} (справочник, графика нет)")
    print(f"   шапка: строки {[i + 1 for i in header_rows]}; данных с файла: {data_start + 1}")
    print(f"   колонка кода: {chr(ord('A') + code_col)}; "
          f"годовые нормы: {[chr(ord('A') + c) for c in year_cols] or 'нет'}")
    print(f"   строк с данными в файле: {len(expect)}; в RAG: {len(got)} "
          f"(без кода в файле: {without_code})")
    problems = len(set(expect) - set(got)) + len(set(got) - set(expect))
    if set(expect) - set(got):
        print(f"     ! потеряны строки: {sorted(set(expect) - set(got))[:MAX_EXAMPLES]}")
    if set(got) - set(expect):
        print(f"     ! лишние строки: {sorted(set(got) - set(expect))[:MAX_EXAMPLES]}")
    inherited = 0
    for (row_number, column), value in merges.items():
        if column - 1 != code_col or row_number in expect:
            continue
        inherited += 1
    if inherited:
        print(f"   объединённых кодов вне строк данных: {inherited}")
    lost = 0
    for number, values in expect.items():
        if number not in got:
            continue
        text = " ".join(str(got[number]["text"]).split())
        for value in values:
            if value and value not in text:
                lost += 1
                if lost <= MAX_EXAMPLES:
                    print(f"     ! строка {number}: значение «{value}» не попало в текст документа")
    print(f"   сверка: потеряно строк {problems}, потеряно значений {lost}")
    return problems + lost


def compare(path: Path, engine: RagEngine) -> int:
    rows_by_sheet = raw_grid(path)
    merges = read_merged_values(path)
    docs = [d for d in engine.docs if d.get("kind") == "row"]
    print(f"файл: {path.name}")
    print(f"RAG: строк-документов {len(docs)}, всего документов {len(engine.docs)}")
    problems = 0

    for sheet, (rows, own) in rows_by_sheet.items():
        month_row, months = month_columns(rows)
        if not months:
            problems += reference_check(rows, docs, sheet, merges.get(sheet, {}), own)
            continue
        code_col = code_column(rows, month_row)
        names = name_columns(rows, month_row)
        expect = expected_rows(rows, month_row, months, code_col, own)
        got = {int(d["meta"]["row"]): d for d in docs if str(d["meta"].get("sheet")) == sheet}

        letters = {num: chr(ord("A") + col) for num, col in sorted(months.items(), key=lambda kv: int(kv[0]))}
        print(f"\n[{sheet}] роль: {kmhto.sheet_role(sheet)}")
        print(f"   строка месяцев: Excel {month_row + 1}; месяцев найдено: {len(months)}")
        print(f"   колонки: код = {chr(ord('A') + code_col)}, "
              f"наименование = {chr(ord('A') + names.get('equipment', -1)) if 'equipment' in names else '?'}, "
              f"место = {chr(ord('A') + names.get('place', -1)) if 'place' in names else '?'}")
        print(f"   месяц -> колонка: " + ", ".join(f"{m}={letters[m]}" for m in sorted(letters, key=int)))
        print(f"   строк с данными в файле: {len(expect)}; в RAG: {len(got)}")

        missing = sorted(set(expect) - set(got))
        extra = sorted(set(got) - set(expect))
        if missing:
            problems += len(missing)
            print(f"   ! потеряны строки: {missing[:MAX_EXAMPLES]}")
        if extra:
            problems += len(extra)
            print(f"   ! лишние строки: {extra[:MAX_EXAMPLES]}")

        bad_code, bad_days, bad_hash = 0, 0, 0
        samples: list[str] = []
        for number, wanted in expect.items():
            doc = got.get(number)
            if doc is None:
                continue
            meta = doc["meta"]
            if str(meta.get("code")) != wanted["code"].rstrip("пП"):
                bad_code += 1
                if len(samples) < MAX_EXAMPLES:
                    samples.append(f"строка {number}: код {meta.get('code')} вместо {wanted['code']}")
            parsed = meta.get("months") or {}
            for num, text in wanted["cells"].items():
                want_days = kmhto.parse_days(text)
                want_to = kmhto.parse_work_items(text)
                month_name = [m for m in parsed if kmhto.month_index(m) == int(num)]
                have = parsed[month_name[0]] if month_name else ""
                have_days = kmhto.parse_days(have)
                have_to = kmhto.parse_work_items(have)
                if (want_days and want_days != have_days) or (want_to and want_to != have_to):
                    bad_days += 1
                    if len(samples) < MAX_EXAMPLES:
                        samples.append(f"строка {number} {have or month_name}: "
                                       f"в файле {want_to or want_days}, в RAG {have_to or have_days}")
            text = " ".join(str(doc["text"]).split())
            for key, field in (("equipment", "Оборудование"), ("place", "Место установки")):
                col = names.get(key)
                if col is None:
                    continue
                raw_value = " ".join(cell_text(rows[number - 1][col]).split())
                if raw_value and f"{field}: {raw_value[:30]}" not in text:
                    bad_hash += 1
                    if len(samples) < MAX_EXAMPLES:
                        samples.append(f"строка {number} {field}: в файле «{raw_value[:40]}», "
                                       f"в тексте RAG нет")
        problems += bad_code + bad_days + bad_hash
        print(f"   сверка: коды неверны {bad_code}, дни/виды ТО неверны {bad_days}, "
              f"поля перепутаны {bad_hash}")
        for line in samples:
            print("     " + line)

    print("\n=== состав RAG ===")
    kinds: dict[str, int] = {}
    for doc in engine.docs:
        kinds[str(doc["kind"])] = kinds.get(str(doc["kind"]), 0) + 1
    print("  по видам:", kinds)
    print("  справочных разделов:", kinds.get("reference", 0),
          "| сводок по кодам:", kinds.get("code_summary", 0))
    print("  кодов оборудования:", len({d["meta"].get("code") for d in docs if d["meta"].get("code")}))
    print("  опечаток/непонятных ячеек:", len(engine.typos), engine.typos[:3])
    return problems


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else config.sample_document()
    if path is None:
        print("укажите файл: tools/audit_document.py путь\\к\\файлу.xlsx")
        return 2
    engine = RagEngine()
    # build(), а не ensure_loaded(): сверяем разбор ТЕКУЩИМ кодом, а не кэш прошлой версии
    engine.build(path)
    problems = compare(path, engine)
    print("\nИТОГ:", "расхождений нет" if problems == 0 else f"расхождений {problems}")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    main()
