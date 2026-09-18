# -*- coding: utf-8 -*-
"""Нормализация текста перед синтезом речи (ru/en) + разбиение на предложения.

Только стандартная библиотека: работает офлайн, без моделей и без интернета.
Что делает:
  * убирает markdown/эмодзи/служебные символы;
  * разворачивает сокращения и латиницу так, как их надо прочитать;
  * превращает числа, даты, время, единицы измерения в слова;
  * чистит текст от того, что синтезатор всё равно не прочитает.
"""
from __future__ import annotations

import re
from typing import Iterable

# ---------------------------------------------------------------------------
# числа: русский
# ---------------------------------------------------------------------------
_RU_UNITS_M = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_RU_UNITS_F = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_RU_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
             "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_RU_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
            "восемьдесят", "девяносто"]
_RU_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
                "восемьсот", "девятьсот"]
_RU_THOUSAND_FORMS = ("тысяча", "тысячи", "тысяч")
_RU_MILLION_FORMS = ("миллион", "миллиона", "миллионов")

_RU_ORDINAL_M = ["", "первый", "второй", "третий", "четвёртый", "пятый", "шестой", "седьмой",
                 "восьмой", "девятый", "десятый", "одиннадцатый", "двенадцатый", "тринадцатый",
                 "четырнадцатый", "пятнадцатый", "шестнадцатый", "семнадцатый", "восемнадцатый",
                 "девятнадцатый"]
_RU_ORDINAL_TENS_M = ["", "", "двадцатый", "тридцатый", "сороковой", "пятидесятый", "шестидесятый",
                      "семидесятый", "восьмидесятый", "девяностый"]
_RU_MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                  "сентября", "октября", "ноября", "декабря"]


def _plural_ru(n: int, forms: Iterable[str]) -> str:
    forms = tuple(forms)
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def num2words_ru(value: int, gender: str = "m") -> str:
    """Число прописью (мужской/женский род). 0..999 999 999."""
    value = int(value)
    if value == 0:
        return "ноль"
    if value < 0:
        return "минус " + num2words_ru(-value, gender)

    def under_1000(num: int, g: str) -> str:
        out: list[str] = []
        u = _RU_UNITS_F if g == "f" else _RU_UNITS_M
        if num >= 100:
            out.append(_RU_HUNDREDS[num // 100])
            num %= 100
        if 10 <= num <= 19:
            out.append(_RU_TEENS[num - 10])
        else:
            if num >= 20:
                out.append(_RU_TENS[num // 10])
                num %= 10
            if num:
                out.append(u[num])
        return " ".join(x for x in out if x)

    parts: list[str] = []
    millions, thousands, rest = value // 1_000_000, (value // 1_000) % 1000, value % 1000
    if millions:
        parts += [under_1000(millions, "m"), _plural_ru(millions, _RU_MILLION_FORMS)]
    if thousands:
        parts += [under_1000(thousands, "f"), _plural_ru(thousands, _RU_THOUSAND_FORMS)]
    if rest:
        parts.append(under_1000(rest, gender))
    return " ".join(x for x in parts if x)


def _ord_form(idx: int, gender: str) -> str:
    """Порядковое 1..19 в нужном роде."""
    if idx == 3:
        return {"m": "третий", "f": "третья", "n": "третье"}[gender]
    masc = _RU_ORDINAL_M[idx]
    if gender == "m":
        return masc
    stem = masc[:-2]  # "...ый"/"...ой" -> основа
    return stem + ("ая" if gender == "f" else "ое")


def ordinal_ru(value: int, gender: str = "n") -> str:
    """Порядковое числительное (для дат — средний род: 'четырнадцатое')."""
    value = int(value)
    if value <= 0:
        return num2words_ru(value, gender)
    if value < 20:
        return _ord_form(value, gender)
    if value < 100:
        tens, units = divmod(value, 10)
        if units == 0:
            masc = _RU_ORDINAL_TENS_M[tens]
            return masc if gender == "m" else masc[:-2] + ("ая" if gender == "f" else "ое")
        # 38-й = «тридцать восьмой» (десятки количественным, последняя — порядковая)
        return f"{_RU_TENS[tens]} " + _ord_form(units, gender)
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        head = _RU_HUNDREDS[hundreds] if hundreds else ""
        return (head + " " + ordinal_ru(rest, gender)).strip() if rest else head
    return num2words_ru(value, "m")


_RU_ORD_GEN_M = ["", "первого", "второго", "третьего", "четвёртого", "пятого", "шестого",
                 "седьмого", "восьмого", "девятого", "десятого", "одиннадцатого", "двенадцатого",
                 "тринадцатого", "четырнадцатого", "пятнадцатого", "шестнадцатого",
                 "семнадцатого", "восемнадцатого", "девятнадцатого"]
_RU_ORD_TENS_GEN_M = ["", "", "двадцатого", "тридцатого", "сорокового", "пятидесятого",
                      "шестидесятого", "семидесятого", "восьмидесятого", "девяностого"]


def ordinal_ru_genitive(value: int) -> str:
    """Порядковое в родительном падеже (мужской род): «шестого», «двадцать шестого»."""
    value = int(value)
    if value <= 0:
        return num2words_ru(value, "m")
    if value < 20:
        return _RU_ORD_GEN_M[value]
    if value < 100:
        tens, units = divmod(value, 10)
        head = _RU_ORD_TENS_GEN_M[tens]
        return head if units == 0 else f"{_RU_TENS[tens]} {_RU_ORD_GEN_M[units]}"
    return ordinal_ru(value, "m")


def year_ru_genitive(year: int) -> str:
    """Год в родительном падеже — как требуют даты: «две тысячи двадцать шестого года»."""
    year = int(year)
    if year == 2000:
        return "двухтысячного"
    if 1900 <= year < 2000:
        tail = year % 100
        return "тысяча девятьсот" + (f" {ordinal_ru_genitive(tail)}" if tail else "ого")
    if 2000 < year < 2100:
        tail = year % 100
        return "две тысячи" + (f" {ordinal_ru_genitive(tail)}" if tail else "")
    return num2words_ru(year, "m")


def _year_ordinal_m(n: int) -> str:
    """Порядковое для года: 26 -> 'двадцать шестой' (а не 'двадцатый шестой')."""
    if n < 20:
        return _ord_form(n, "m")
    tens, units = divmod(n, 10)
    if units == 0:
        return _RU_ORDINAL_TENS_M[tens]
    return f"{_RU_TENS[tens]} {_ord_form(units, 'm')}"


def year_ru(year: int) -> str:
    """Год так, как его произносят: 2001 -> 'две тысячи первый'."""
    year = int(year)
    if year == 2000:
        return "двухтысячный"
    if 1900 <= year < 2000:
        tail = year % 100
        return "тысяча девятьсот" + (f" {_year_ordinal_m(tail)}" if tail else "ый")
    if 2000 < year < 2100:
        tail = year % 100
        return "две тысячи" + (f" {_year_ordinal_m(tail)}" if tail else "")
    return num2words_ru(year, "m")


# ---------------------------------------------------------------------------
# числа: английский
# ---------------------------------------------------------------------------
_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_EN_ORDINAL = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
               "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
               "sixteenth", "seventeenth", "eighteenth", "nineteenth"]


def num2words_en(value: int) -> str:
    value = int(value)
    if value < 0:
        return "minus " + num2words_en(-value)
    if value < 20:
        return _EN_ONES[value]
    if value < 100:
        tens, units = divmod(value, 10)
        return _EN_TENS[tens] + (f"-{_EN_ONES[units]}" if units else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return _EN_ONES[hundreds] + " hundred" + (f" {num2words_en(rest)}" if rest else "")
    for div, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")):
        if value >= div:
            head, rest = divmod(value, div)
            return f"{num2words_en(head)} {name}" + (f" {num2words_en(rest)}" if rest else "")
    return str(value)


def ordinal_en(value: int) -> str:
    value = int(value)
    if value < 20:
        return _EN_ORDINAL[value]
    if value < 100:
        tens, units = divmod(value, 10)
        if units == 0:
            return _EN_TENS[tens][:-1] + "ieth"
        return f"{_EN_TENS[tens]}-{_EN_ORDINAL[units]}"
    return num2words_en(value) + "th"


# ---------------------------------------------------------------------------
# сокращения, символы, единицы
# ---------------------------------------------------------------------------
# Сокращения-слова (без чисел). Единицы измерения — отдельно, ниже: они согласуются с числом.
_ABBREV_RU: list[tuple[str, str]] = [
    ("СИКН", "сикэн"),
    ("КИПиА", "кипиа"),
    ("АСУ ТП", "а эс у тэ пэ"),
    ("БИК", "бик"),
    ("ИВК", "и вэ ка"),
    ("СОИ", "с о и"),
    ("ИБП", "и бэ пэ"),
    ("ТПР", "тэ пэ эр"),
    ("КМХ", "кэ эм ха"),
    ("АСН", "а эс эн"),
    ("ГОСТ", "гост"),
    ("ТУ", "тэ у"),
    ("ИЛ", "и эл"),
    ("СИ", "эс и"),
    ("Ду", "ду"),
    ("DN", "ду"),
    ("PN", "пэ эн"),
]

# Единицы измерения: три формы — для 1, для 2–4 и для 5+.
# Именно это даёт правильные окончания: «20 мегапаскалей», «2 мегапаскаля», «6,3 мегапаскаля».
# Порядок важен: составные единицы идут раньше одиночных.
_UNITS_RU: list[tuple[str, str, str, str]] = [
    ("м³/ч", "кубометр в час", "кубометра в час", "кубометров в час"),
    ("м3/ч", "кубометр в час", "кубометра в час", "кубометров в час"),
    ("кг/м³", "килограмм на кубический метр", "килограмма на кубический метр",
     "килограммов на кубический метр"),
    ("кг/м3", "килограмм на кубический метр", "килограмма на кубический метр",
     "килограммов на кубический метр"),
    ("об/мин", "оборот в минуту", "оборота в минуту", "оборотов в минуту"),
    ("°C", "градус Цельсия", "градуса Цельсия", "градусов Цельсия"),
    ("°С", "градус Цельсия", "градуса Цельсия", "градусов Цельсия"),
    ("МПа", "мегапаскаль", "мегапаскаля", "мегапаскалей"),
    ("кПа", "килопаскаль", "килопаскаля", "килопаскалей"),
    ("кВт", "киловатт", "киловатта", "киловатт"),
    ("МГц", "мегагерц", "мегагерца", "мегагерц"),
    ("ГГц", "гигагерц", "гигагерца", "гигагерц"),
    ("Гц", "герц", "герца", "герц"),
    ("кВ", "киловольт", "киловольта", "киловольт"),
    ("мА", "миллиампер", "миллиампера", "миллиампер"),
    ("м²", "квадратный метр", "квадратных метра", "квадратных метров"),
    ("м³", "кубический метр", "кубических метра", "кубических метров"),
    ("м3", "кубический метр", "кубических метра", "кубических метров"),
    ("мм", "миллиметр", "миллиметра", "миллиметров"),
    ("кг", "килограмм", "килограмма", "килограммов"),
    ("км", "километр", "километра", "километров"),
    ("%", "процент", "процента", "процентов"),
    ("шт", "штука", "штуки", "штук"),
    ("руб", "рубль", "рубля", "рублей"),
    ("мин", "минута", "минуты", "минут"),
    ("ч", "час", "часа", "часов"),
    ("т", "тонна", "тонны", "тонн"),
    ("л", "литр", "литра", "литров"),
    ("м", "метр", "метра", "метров"),
    ("с", "секунда", "секунды", "секунд"),
]

# Латинские аббревиатуры читаем по буквам русскими названиями: FH -> «эф-эйч».
_LATIN_LETTERS = {
    "A": "эй", "B": "би", "C": "си", "D": "ди", "E": "и", "F": "эф", "G": "джи", "H": "эйч",
    "I": "ай", "J": "джей", "K": "кей", "L": "эл", "M": "эм", "N": "эн", "O": "оу", "P": "пи",
    "Q": "кью", "R": "ар", "S": "эс", "T": "ти", "U": "ю", "V": "ви", "W": "дабл-ю",
    "X": "экс", "Y": "уай", "Z": "зет",
}
# Известные бренды/марки читаются как принято, а не по буквам
_LATIN_WORDS = {"CD": "си-ди", "MB": "эм-би", "ID": "ай-ди", "AC": "эй-си"}
_LATIN_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,4})(?![A-Za-z0-9])")
_ABBREV_EN: list[tuple[str, str]] = [
    ("m3/h", " cubic meters per hour"),
    ("m3", " cubic meters"),
    ("kg/m3", " kilograms per cubic meter"),
    ("°C", " degrees Celsius"),
    ("№", " number "),
    ("&", " and "),
]

_SYMBOL_RU = [("№", " номер "), ("±", " плюс-минус "), ("&", " и ")]
_SYMBOL_EN = [("%", " percent ")]

_EMOJI_RE = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002700-\U000027BF" "\U0001F000-\U0001F2FF"
    "\U00002600-\U000026FF" "\U0001F900-\U0001F9FF" "\u2b00-\u2bff" "\u2190-\u21ff" "\ufe0f" "\u20e3" "]",
    flags=re.UNICODE,
)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_DECOR_RE = re.compile(r"(\*\*|__|\*|_|[\x60]{1,3}|^#{1,6}\s*)", flags=re.MULTILINE)
_WS_RE = re.compile(r"[ \t\u00a0]+")
_NL_RE = re.compile(r"\n{2,}")
_SLASH_RE = re.compile(r"(?<=[0-9A-Za-zА-Яа-яЁё])\s*/\s*(?=[0-9A-Za-zА-Яа-яЁё])")
_ALLOWED_RE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё \t\n.,!?;:()«»\"'\-—–/]")

_HAS_LATIN_RE = re.compile(r"[A-Za-z]")
_HAS_CYR_RE = re.compile(r"[А-Яа-яЁё]")
_CYR_WORD_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё\-]*")


def detect_lang(text: str, default: str = "ru") -> str:
    """Простой определитель языка: по доле кириллицы и латиницы."""
    cyr = len(_HAS_CYR_RE.findall(text))
    lat = len(_HAS_LATIN_RE.findall(text))
    if cyr == 0 and lat == 0:
        return default
    return "ru" if cyr >= lat else "en"


def strip_markup(text: str) -> str:
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_DECOR_RE.sub("", text)
    text = _EMOJI_RE.sub(" ", text)
    return text.replace("\u200b", "").replace("\ufeff", "")


def _apply_abbrev(text: str, table: list[tuple[str, str]]) -> str:
    for src, dst in table:
        pattern = r"(?<![0-9A-Za-zА-Яа-яЁё])" + re.escape(src) + r"(?![0-9A-Za-zА-Яа-яЁё])"
        text = re.sub(pattern, dst, text)
    return text


def _apply_symbols(text: str, table: list[tuple[str, str]]) -> str:
    for src, dst in table:
        text = text.replace(src, dst)
    return text


def _ru_dates(text: str) -> str:
    def ddmm3(m: re.Match) -> str:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        out = f"{ordinal_ru(d, 'n')} {_RU_MONTHS_GEN[mo]}"
        if y:
            full = y if y > 100 else 2000 + y
            out += " " + year_ru_genitive(full) + " года"
        return out

    # Только ПОЛНАЯ дата дд.мм.гггг: короткую "5.2" нельзя считать датой,
    # иначе ломаются номера пунктов ГОСТ и десятичные дроби.
    return re.sub(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b", ddmm3, text)


def _ru_time(text: str) -> str:
    def hhmm(m: re.Match) -> str:
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return m.group(0)
        out = f"{num2words_ru(h, 'm')} {_plural_ru(h, ('час', 'часа', 'часов'))}"
        if mi:
            out += (f" {num2words_ru(mi, 'f')} "
                    f"{_plural_ru(mi, ('минута', 'минуты', 'минут'))}")
        return out

    return re.sub(r"\b(\d{1,2}):(\d{2})\b", hhmm, text)


def _ru_specific_tokens(text: str) -> str:
    """Специфика СИКН: ТО-N, DN-число, ГОСТ."""
    text = re.sub(
        r"\bТО[-–\s]?([1-3])\s*\(\s*(\d{1,2})\s*\)",
        lambda m: f"тэ о {num2words_ru(int(m.group(1)))}, {ordinal_ru(int(m.group(2)), 'n')}",
        text,
    )
    text = re.sub(r"\bТО[-–]?([1-3])\b", lambda m: "тэ о " + num2words_ru(int(m.group(1))), text)
    text = re.sub(r"\bТО\b", "тэ о", text)
    text = re.sub(r"\b(?:DN|Ду)\s*(\d+)", lambda m: "ду " + num2words_ru(int(m.group(1))), text)
    text = re.sub(r"\bГОСТ\s*([\d.,\-]+)", lambda m: "гост " + _ru_number_series(m.group(1)), text)
    return text


# «зав.№ 000103», «зав. № 123», «заводской номер: 123» — значение заводского номера
# вслух не читаем: произносим только «заводской номер», цифры выбрасываем.
_SERIAL_RE = re.compile(
    r"\bзав(?:одск\w*)?\.?\s*(?:№|номер|ном\.?)\s*[:№]?\s*[\w\-/]*",
    re.IGNORECASE)


_SERIAL_MARK = "\u241f"                       # временная метка вместо номера
_SENT_BOUNDARY_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _ru_serials(text: str) -> str:
    """Значения заводских номеров вслух не читаем.

    Один номер в предложении -> «заводской номер», несколько -> «заводские номера»
    (один раз, повторы в перечислении убираем, чтобы речь не заикалась).
    """
    marked = _SERIAL_RE.sub(_SERIAL_MARK, text)
    if _SERIAL_MARK not in marked:
        return text
    pieces: list[str] = []
    for piece in _SENT_BOUNDARY_RE.split(marked):
        count = piece.count(_SERIAL_MARK)
        if count == 0:
            pieces.append(piece)
        elif count == 1:
            pieces.append(piece.replace(_SERIAL_MARK, "заводской номер"))
        else:
            head, tail = piece.split(_SERIAL_MARK, 1)
            pieces.append(head + "заводские номера" + tail.replace(_SERIAL_MARK, ""))
    result = " ".join(pieces)
    result = re.sub(r"\s*,\s*(?=[,;.!?])", "", result)   # «прибор, ;» -> «прибор;»
    result = re.sub(r"\s*;\s*(?=[.!?,;])", ";", result)
    result = re.sub(r"\s+([,;.!?])", r"\1", result)
    result = re.sub(r"([,;])\1+", r"\1", result)
    result = re.sub(r"\(\s*\)", "", result)
    return result


def _ru_number_series(raw: str) -> str:
    """'8.611' -> 'восемь шестьсот одиннадцать' (как читают номера стандартов)."""
    out: list[str] = []
    for chunk in re.split(r"[.,\-]", raw):
        if not chunk:
            continue
        try:
            out.append(num2words_ru(int(chunk)))
        except ValueError:
            out.append(chunk)
    return " ".join(out)


_RU_DENOM = {1: "десятых", 2: "сотых", 3: "тысячных", 4: "десятитысячных", 5: "стотысячных"}


def _ru_decimal(whole: str, frac: str) -> str:
    digits = len(frac)
    out = (num2words_ru(int(whole), "f") if whole else "ноль") + " целых "
    if digits <= 3:
        return out + num2words_ru(int(frac), "f") + " " + _RU_DENOM.get(digits, "десятых")
    return out + " ".join(num2words_ru(int(c), "f") for c in frac)


def _ru_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(0).replace(",", ".")
        try:
            if "." in raw:
                whole, frac = raw.split(".", 1)
                return _ru_decimal(whole, frac.rstrip("0") or "0")
            return num2words_ru(int(raw))
        except ValueError:
            return m.group(0)

    return re.sub(r"(?<![A-Za-zА-Яа-яЁё0-9])\d+(?:[.,]\d+)?(?![A-Za-zА-Яа-яЁё0-9])", repl, text)


def _en_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(0)
        try:
            if "." in raw:
                whole, frac = raw.split(".", 1)
                digits = " ".join(_EN_ONES[int(c)] for c in frac if c.isdigit())
                return f"{num2words_en(int(whole))} point {digits}"
            return num2words_en(int(raw))
        except (ValueError, IndexError):
            return raw

    return re.sub(r"(?<![A-Za-zА-Яа-яЁё0-9])\d+(?:\.\d+)?(?![A-Za-zА-Яа-яЁё0-9])", repl, text)


def _unit_form(raw_number: str) -> int:
    """0 — форма для 1, 1 — для 2–4, 2 — для 5+ (по правилам русского счёта)."""
    if "," in raw_number or "." in raw_number:
        return 1                       # с дробью — родительный единственного: «6,3 мегапаскаля»
    try:
        value = abs(int(raw_number))
    except ValueError:
        return 2
    value %= 100
    if 11 <= value <= 14:
        return 2
    value %= 10
    if value == 1:
        return 0
    if 2 <= value <= 4:
        return 1
    return 2


def _ru_units(text: str) -> str:
    """Согласует единицы измерения с числом: «20 МПа» -> «20 мегапаскалей».

    Раньше единица переводилась всегда в одну форму («20 мегапаскаль») — это и была
    основная ошибка окончаний.
    """
    for unit, one, few, many in _UNITS_RU:
        forms = (one, few, many)
        pattern = re.compile(
            r"(\d+(?:[.,]\d+)?)\s*" + re.escape(unit)
            + r"(?![0-9A-Za-zА-Яа-яЁё.])(?!\s+половин)")
        text = pattern.sub(lambda m: m.group(1) + " " + forms[_unit_form(m.group(1))], text)
    # единица без числа — только многосимвольные (односимвольные вроде «с» бывают предлогом)
    for unit, one, _few, _many in _UNITS_RU:
        if len(unit) < 2:
            continue
        text = re.sub(r"(?<![0-9A-Za-zА-Яа-яЁё])" + re.escape(unit) + r"(?![0-9A-Za-zА-Яа-яЁё.])",
                      one, text)
    return text


_RU_MONTHS_ALT = "|".join(m for m in _RU_MONTHS_GEN[1:])
# После этих предлогов день месяца читается в родительном падеже: «с первого мая».
_GENITIVE_PREP_RE = re.compile(r"\b(с|со|от|до|после|около)\s+$", re.IGNORECASE)
# А после «к» — в дательном: «к первому мая».
_DATIVE_PREP_RE = re.compile(r"\bк\s+$", re.IGNORECASE)


def _ru_written_dates(text: str) -> str:
    """«17 сентября 2001 года» -> «семнадцатое сентября две тысячи первого года».

    Год в дате обязан быть в родительном падеже — иначе получается «две тысячи двадцать
    шесть года», что звучит неграмотно.
    """
    pattern = re.compile(r"\b(\d{1,2})\s+(" + _RU_MONTHS_ALT + r")(?:\s+(\d{4}))?\s*(?:года|год|г\.)?",
                         re.IGNORECASE)

    def repl(m: re.Match) -> str:
        day = int(m.group(1))
        if not 1 <= day <= 31:
            return m.group(0)
        before = text[:m.start()]
        if _GENITIVE_PREP_RE.search(before):
            day_words = ordinal_ru_genitive(day)                   # с первого мая
        elif _DATIVE_PREP_RE.search(before):
            day_words = ordinal_ru_genitive(day)[:-2] + "ому"      # к первому мая
        else:
            day_words = ordinal_ru(day, "n")                       # первое мая
        out = f"{day_words} {m.group(2).lower()}"
        if m.group(3):
            out += " " + year_ru_genitive(int(m.group(3))) + " года"
        return out

    return pattern.sub(repl, text)


# Год читаем словами только когда рядом есть маркер: «2001 года», «2001 г.».
# Иначе любое четырёхзначное число («1234 м³/ч») превратилось бы в год.
_YEAR_WORD_RE = re.compile(r"\b(\d{4})\s*(года|год|г\.)(?![0-9А-Яа-яЁё])")
_DASH_ORD_RE = re.compile(r"\b(\d{1,3})\s*-\s*(я|й|е|го|му|ом|ая|ое|ой|ые|ых|ым|ыми|ый)\b",
                          re.IGNORECASE)


def _ru_years(text: str) -> str:
    """«2001 года» -> «две тысячи первого года», «2001 г.» -> «... первый год»."""
    def repl(m: re.Match) -> str:
        year = int(m.group(1))
        if not 1000 <= year <= 2200:
            return m.group(0)
        suffix = m.group(2).lower()
        if suffix == "года":
            return f"{year_ru_genitive(year)} года"
        return f"{year_ru(year)} год"

    return _YEAR_WORD_RE.sub(repl, text)


def _ru_dash_ordinals(text: str) -> str:
    """«38-я неделя» -> «тридцать восьмая неделя», «3-й квартал» -> «третий квартал»."""
    plural_end = {"ые": "ые", "ых": "ых", "ым": "ым", "ыми": "ыми", "ом": "ом"}

    def repl(m: re.Match) -> str:
        num = int(m.group(1))
        suffix = m.group(2).lower()
        if suffix in ("я", "ая", "ой"):
            return ordinal_ru(num, "f")
        if suffix in ("й", "ый"):
            return ordinal_ru(num, "m")
        if suffix in ("е", "ое"):
            return ordinal_ru(num, "n")
        if suffix == "го":
            return ordinal_ru_genitive(num)
        if suffix == "му":
            return ordinal_ru_genitive(num)[:-2] + "ому"
        if suffix in plural_end:
            base = ordinal_ru(num, "m")
            return base[:-2] + plural_end[suffix]
        return ordinal_ru(num, "m")

    return _DASH_ORD_RE.sub(repl, text)


def _ru_latin(text: str) -> str:
    """Латинские аббревиатуры — по буквам русскими названиями: FH -> «эф-эйч»."""
    def repl(m: re.Match) -> str:
        word = m.group(1)
        if word in _LATIN_WORDS:
            return _LATIN_WORDS[word]
        names = [_LATIN_LETTERS.get(ch) for ch in word]
        if any(name is None for name in names):
            return word
        return "-".join(names)          # type: ignore[arg-type]

    return _LATIN_ACRONYM_RE.sub(repl, text)


def normalize_for_speech(text: str, lang: str = "auto") -> str:
    """Главная функция: текст, готовый к озвучке."""
    if not text:
        return ""
    text = strip_markup(text)
    if lang == "auto":
        lang = detect_lang(text)
    if lang == "ru":
        text = _ru_serials(text)              # «зав.№ 902295» -> «заводской номер»
        text = _apply_symbols(text, _SYMBOL_RU)
        text = _ru_specific_tokens(text)      # ТО-1, DN100, ГОСТ
        text = _ru_units(text)                # согласование единиц с числом
        text = _apply_abbrev(text, _ABBREV_RU)
        text = _ru_written_dates(text)        # «17 сентября 2001 года»
        text = _ru_dates(text)                # «17.09.2001»
        text = _ru_years(text)                # «2001 года», «2001 г.»
        text = _ru_dash_ordinals(text)        # «38-я», «3-й»
        text = _ru_time(text)
        text = _ru_numbers(text)
        text = _ru_latin(text)                # FH -> «эф-эйч»
    else:
        text = _apply_abbrev(text, _ABBREV_EN)
        text = _apply_symbols(text, _SYMBOL_EN)
        text = _en_numbers(text)
    text = _SLASH_RE.sub(" на " if lang == "ru" else " per ", text)
    text = _ALLOWED_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = _NL_RE.sub("\n", text)
    return text.strip()


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])[\s\n]+|(?<=[;:])\s+|\n+")


def split_sentences(text: str, max_len: int = 220, merge: bool = True) -> list[str]:
    """Режет текст на удобные для синтеза куски, стараясь не рвать предложения.

    merge=False — вернуть предложения по отдельности (нужно, чтобы читать русский и
    английский текст разными голосами).
    """
    text = (text or "").strip()
    if not text:
        return []
    rough = [p.strip() for p in _SENT_SPLIT_RE.split(text) if p and p.strip()]
    if not merge:
        out: list[str] = []
        for part in rough:
            while len(part) > max_len:
                head, tail = part[:max_len], part[max_len:]
                cut = head.rfind(" ")
                if cut < max_len // 2:
                    cut = len(head)
                out.append(head[:cut].strip())
                part = (head[cut:] + tail).strip()
            if part:
                out.append(part)
        return out
    chunks: list[str] = []
    current = ""
    for part in rough:
        while len(part) > max_len:
            head, tail = part[:max_len], part[max_len:]
            cut = head.rfind(" ")
            if cut < max_len // 2:
                cut = len(head)
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head[:cut].strip())
            part = (head[cut:] + tail).strip()
            if not part:
                break
        if not part:
            continue
        if not current:
            current = part
        elif len(current) + 1 + len(part) <= max_len:
            current = f"{current} {part}"
        else:
            chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


if __name__ == "__main__":
    print("--- RU ---")
    for c in [
        "Привет! Сегодня 14.02.2001, температура +20 °C и давление 6,3 МПа.",
        "Преобразователь расхода, зав. № 000103, установка № 1",
        "Датчик давления, зав.№ 000101, поверка",
        "Шкаф электроники, заводской номер: 000104, ТО-3 (16)",
        "ТО-1 (14) и ТО-3 (07) выполняются по графику",
        "ГОСТ 8.611-2013, пункт 5.2",
        "Объём 1234 м³/ч, плотность 850 кг/м³, время 08:30",
        "**Жирный** и _курсив_ и [ссылка](http://x) 😀",
        "Погрешность ±0,5 %",
    ]:
        print(" ", normalize_for_speech(c, "ru"))
    print("--- EN ---")
    for c in ["Flow is 1234 m3/h at 20 °C", "See item 5.2, page 14"]:
        print(" ", normalize_for_speech(c, "en"))
    print("--- helpers ---")
    print("  split:", split_sentences("Первое предложение. Второе, которое чуть длиннее! Третье?", 30))
    print("  year:", year_ru(2001), "| ordinal:", ordinal_ru(14, "n"), "| num:", num2words_ru(1234))
