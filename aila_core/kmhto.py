# -*- coding: utf-8 -*-
"""Парсер и описание документа графика ТО/КМХ.

Взято из проекта SN1054NGC/kmhto (файлы TZ.md и REPORT.md): там описана структура
того же формата документа и правила разбора «грязных» данных.

Что даёт модуль нашему поиску:
  * лист определяется по роли: 1 — график ТО, 3 — график КМХ (дни контроля),
    data / коды — справочник оборудования;
  * семантика: колонка = месяц, ячейка = список дней месяца, строка = оборудование;
  * дни из ячеек разбираются устойчиво: переносы строк, смешанные разделители
    (запятая, точка с запятой, слэш, пробел), хвостовые разделители, лишние пробелы,
    мягкие переносы, похожие кириллические и латинские буквы;
  * недопустимые дни (0 или > 31) отбрасываются и попадают в отчёт об опечатках;
  * колонки ищутся по ИМЕНАМ — вставка столбцов в документ разбор не ломает.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# описание документа (идёт в системный промпт модели и в базу знаний)
# ---------------------------------------------------------------------------
DOCUMENT_INFO = (
    "ДОКУМЕНТ «ГРАФИК ТО/КМХ» (формат ТОКМХ):\n"
    "• Лист «1» — график технического обслуживания: в ячейках месяцев указаны виды "
    "работ в виде «ТО-1 (день)», «ТО-2 (день)», «ТО-3 (день)».\n"
    "• Лист «3» — график КМХ (контроль метрологических характеристик, поверка/калибровка): "
    "в ячейках месяцев перечислены ДНИ месяца, их может быть несколько в одной ячейке.\n"
    "• Лист «data» или «коды» — справочник оборудования: код, наименование, работы при "
    "ТО-1/ТО-2/ТО-3, количество работ в год, нормы времени и ссылка на технологическую карту.\n"
    "• Семантика: колонка = месяц, ячейка = список дней месяца, строка = оборудование.\n"
    "• ТО — техническое обслуживание; ТО-1, ТО-2, ТО-3 — его виды (ТО-3 самое полное и редкое). "
    "Число в скобках — это ДЕНЬ месяца, в который проводится этот вид работ: «ТО-3 (20)» = "
    "ТО-3 двадцатого числа. Под названиями месяцев в файле для этого стоит пояснение «(число)». "
    "Не путай это число с количеством работ в год — оно берётся из листа-справочника.\n"
    "• Колонки месяцев идут по порядку: январь, февраль, …, декабрь — 12 колонок, по имени "
    "месяца; буквы колонок в разных листах отличаются, ориентируйся на название месяца.\n"
    "• ГОД в документе: колонки — только месяцы, явного года в файле нет. Если спросят про год "
    "графика — так и отвечай: год в документе не указан, есть только месяцы (не подставляй "
    "текущий год как год документа).\n"
    "• ТО и КМХ — РАЗНЫЕ графики, в планировании участвуют совместно; не путай даты контроля "
    "(лист 3) с видами ТО (лист 1).\n"
    "• Поле «Объект» — это значение колонки «Место установки» дословно.\n"
    "• Первые четыре колонки описательные: № п/п, код СИ/оборудования, наименование, "
    "место установки."
)

# ---------------------------------------------------------------------------
# нормализация «грязных» значений
# ---------------------------------------------------------------------------
_SOFT = "\u00ad\u200b\ufeff"                      # мягкий перенос, нулевой пробел, BOM
_LOOKALIKE = str.maketrans({
    # латиница -> кириллица (частые подмены в ручном вводе)
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М", "O": "О",
    "P": "Р", "T": "Т", "X": "Х", "Y": "У", "a": "а", "c": "с", "e": "е", "o": "о",
    "p": "р", "x": "х", "y": "у",
    # разные виды дефисов
    "–": "-", "—": "-", "−": "-", "‑": "-",
})

# Месяцы — часть формата документа, поэтому определение живёт здесь
MONTH_WORDS = ("январ", "феврал", "март", "апрел", "май", "июн", "июл", "август",
               "сентябр", "октябр", "ноябр", "декабр")

_DAYS_SPLIT_RE = re.compile(r"[^0-9]+")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_WORK_RE = re.compile(r"(ТО\s*[-–]?\s*[1-3]|КМХ|ТО\b)\s*(?:\(\s*(\d{1,3})\s*\))?", re.IGNORECASE)


def column_letter(index: int) -> str:
    """Буква колонки Excel по её номеру (0 -> A)."""
    if index < 0:
        return "?"
    letters = ""
    number = index + 1
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def document_year(rows: list[list[Any]], header_rows: Iterable[int] = ()) -> int | None:
    """Год из шапки/заголовка документа (None — явного года в файле нет).

    Смотрим только шапку и строки над ней: годы внутри наименований оборудования —
    это заводские номера, а не год графика.
    """
    heads = list(header_rows)
    limit = min(heads) if heads else 0
    found: dict[int, int] = {}
    for index in range(0, min(len(rows), limit + 1)):
        for value in rows[index]:
            for match in _YEAR_RE.finditer(normalize_text(value)):
                year = int(match.group(1))
                found[year] = found.get(year, 0) + 1
    if not found:
        return None
    return max(found.items(), key=lambda item: item[1])[0]


def is_month_header(head: str) -> bool:
    """Является ли заголовок колонки названием месяца."""
    low = (head or "").lower()
    return any(word in low for word in MONTH_WORDS)


def month_index(head: str) -> int:
    """Номер месяца 1..12 по заголовку колонки (0 — не месяц)."""
    low = (head or "").lower()
    for idx, word in enumerate(MONTH_WORDS, start=1):
        if word in low:
            return idx
    return 0


def normalize_text(value: Any) -> str:
    """Убрать переносы, мягкие переносы и подмены похожих букв."""
    if value is None:
        return ""
    text = str(value)
    for ch in _SOFT:
        text = text.replace(ch, "")
    text = text.translate(_LOOKALIKE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


def parse_days(value: Any) -> list[int]:
    """Дни месяца из ячейки: «14,\\n20,\\n2», «12,22 27  », «14, 20, 2,» -> [2, 14, 20].

    Недопустимые значения (0 и > 31) отбрасываются.
    """
    text = normalize_text(value)
    if not text:
        return []
    days: set[int] = set()
    for chunk in _DAYS_SPLIT_RE.split(text):
        if not chunk:
            continue
        try:
            day = int(chunk)
        except ValueError:
            continue
        if 1 <= day <= 31:
            days.add(day)
    return sorted(days)


def parse_work_items(value: Any) -> list[tuple[str, int | None]]:
    """Виды работ из ячейки листа 1: «ТО-3(10)» -> [("ТО-3", 10)]."""
    text = normalize_text(value)
    if not text:
        return []
    items: list[tuple[str, int | None]] = []
    for match in _WORK_RE.finditer(text):
        raw, day = match.group(1), match.group(2)
        token = re.sub(r"\s+", "", raw).upper().replace("–", "-")
        if token.startswith("КМХ"):
            kind = "КМХ"
        else:
            digit = re.search(r"[1-3]", token)
            kind = f"ТО-{digit.group(0)}" if digit else "ТО"
        day_value: int | None = None
        if day is not None:
            parsed_day = int(day)
            if 1 <= parsed_day <= 31:
                day_value = parsed_day
        items.append((kind, day_value))
    return items


def sheet_role(sheet_name: str, headers: Iterable[str] = ()) -> str:
    """Роль листа: to (график ТО), kmx (график КМХ), ref (справочник), other."""
    name = (sheet_name or "").strip().lower()
    heads = " ".join(normalize_text(h).lower() for h in headers)
    if name in ("1", "то", "tо") or "вид" in heads and "то-" in heads:
        return "to"
    if name in ("3", "кмх") or "кмх" in name or "контрол" in heads or "дат" in heads:
        return "kmx"
    if name in ("data", "коды", "справочник") or "наимен" in heads and "норм" in heads:
        return "ref"
    return "other"


def find_header_block(rows: list[list[Any]], max_scan: int = 10) -> tuple[list[int], int]:
    """Строки шапки и первая строка данных (учитывает пустые строки и многострочные шапки)."""
    def filled(row: Iterable[Any]) -> int:
        return sum(1 for value in row if normalize_text(value))

    head = 0
    while head < len(rows) and filled(rows[head]) < 2:
        head += 1

    month_row, score = None, 0
    for index in range(head, min(len(rows), head + 6)):
        hits = sum(1 for value in rows[index]
                   if is_month_header(normalize_text(value)))
        if hits > score:
            month_row, score = index, hits

    if month_row is None or score < 2:
        return [head], head + 1

    last = month_row
    # строка-пояснение «(число)» сразу под месяцами тоже относится к шапке
    if month_row + 1 < len(rows) and _is_units_row(rows[month_row + 1]):
        last = month_row + 1
    return list(range(head, last + 1)), last + 1


def _is_units_row(row: Iterable[Any]) -> bool:
    filled = [v for v in (normalize_text(x) for x in row) if v]
    if len(filled) < 2:
        return False
    for value in filled:
        if len(value) > 24:
            return False
        if re.search(r"\d", value) and not (value.startswith("(") and value.endswith(")")):
            return False
    return True


def typo_report(rows: list[list[Any]], month_columns: dict[int, str],
                role: str = "kmx") -> list[str]:
    """Отчёт об опечатках: что в документе разобрать не удалось."""
    problems: list[str] = []
    for index, row in enumerate(rows, start=1):
        for column, month in month_columns.items():
            if column >= len(row):
                continue
            raw = normalize_text(row[column])
            if not raw:
                continue
            if role == "to":
                items = parse_work_items(raw)
                if not items or all(day is None for _kind, day in items):
                    problems.append(f"строка {index}, {month}: не разобран вид ТО — {raw[:40]!r}")
            else:
                days = parse_days(raw)
                if not days:
                    problems.append(f"строка {index}, {month}: нет допустимых дней — {raw[:40]!r}")
                elif re.search(r"\b(0|3[2-9]|[4-9]\d)\b", raw):
                    problems.append(f"строка {index}, {month}: недопустимый день — {raw[:40]!r}")
    return problems


def describe_document(sheets: list[dict[str, Any]]) -> str:
    """Карта разобранного документа — короткое описание для модели."""
    if not sheets:
        return ""
    lines = ["СТРУКТУРА ЗАГРУЖЕННОГО ДОКУМЕНТА:"]
    years: list[int] = sorted({int(sheet["year"]) for sheet in sheets if sheet.get("year")})
    for sheet in sheets:
        role_names = {"to": "график ТО", "kmx": "график КМХ (дни контроля)",
                      "ref": "справочник оборудования", "other": "данные"}
        role = role_names.get(str(sheet.get("role") or "other"), "данные")
        parts = [f"лист «{sheet.get('name')}» — {role}",
                 f"строк данных: {sheet.get('rows', 0)}"]
        if sheet.get("months"):
            months = f"месяцев: {sheet['months']}"
            if sheet.get("month_start") and isinstance(sheet.get("months"), int):
                last = column_letter(ord(sheet["month_start"]) - ord("A") + int(sheet["months"]) - 1)
                months += f" (колонки {sheet['month_start']}–{last}: январь → декабрь)"
            parts.append(months)
        if sheet.get("columns"):
            parts.append("колонки: " + ", ".join(sheet["columns"][:6]))
        if sheet.get("codes"):
            parts.append(f"кодов: {sheet['codes']}")
        lines.append("• " + "; ".join(parts))
    if years:
        lines.append("• год документа: " + ", ".join(str(year) for year in years))
    else:
        lines.append("• год документа: в файле НЕ указан (колонки — только месяцы; "
                     "не подставляй текущий год)")
    return "\n".join(lines)


if __name__ == "__main__":
    print("--- разбор дней из «грязных» ячеек ---")
    for raw in ("14,\n20,\n2", "14,20,2,", "12,22\n27  ", "14; 20 / 2", "0, 32, 5", "  "):
        print(f"  {raw!r:20} -> {parse_days(raw)}")
    print("--- разбор видов ТО ---")
    for raw in ("ТО-3 (20)", "ТО-3(10)", "ТО-3( 10 )", "ТО-1 (2)", "КМХ (12)", "ТO-1 (14)"):
        print(f"  {raw!r:16} -> {parse_work_items(raw)}")
    print("--- роли листов ---")
    for name in ("1", "3", "data", "коды", "лист4"):
        print(f"  {name!r:8} -> {sheet_role(name)}")
    print("--- колонки и год ---")
    print("  буквы колонок:", [column_letter(i) for i in (0, 4, 15, 26)])
    demo = [["", "", "", "", "январь", "февраль"], ["", "", "", "", "ТО-1 (5)", "ТО-2 (9)"]]
    print("  год пустого документа:", document_year(demo, [0]))
    titled = [["График ТО на 2001 год"], ["код", "январь"], ["1", "ТО-1 (5)"]]
    print("  год документа с заголовком:", document_year(titled, [1]))
    print("--- описание документа ---")
    print(DOCUMENT_INFO[:200] + "…")
