# -*- coding: utf-8 -*-
"""Число прописью (именительный падеж) на русском и казахском, 0..99999.
Нужно для листа-заверителя: «150 (сто пятьдесят) листов»."""

_RU_UNITS = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь",
             "восемь", "девять"]
_RU_UNITS_F = ["ноль", "одна", "две", "три", "четыре", "пять", "шесть", "семь",
               "восемь", "девять"]
_RU_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
             "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать",
             "девятнадцать"]
_RU_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
            "семьдесят", "восемьдесят", "девяносто"]
_RU_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
                "шестьсот", "семьсот", "восемьсот", "девятьсот"]

_KZ_UNITS = ["нөл", "бір", "екі", "үш", "төрт", "бес", "алты", "жеті",
             "сегіз", "тоғыз"]
_KZ_TENS = ["", "он", "жиырма", "отыз", "қырық", "елу", "алпыс", "жетпіс",
            "сексен", "тоқсан"]


def _ru_triple(n: int, feminine: bool = False) -> list[str]:
    words = []
    if n >= 100:
        words.append(_RU_HUNDREDS[n // 100])
        n %= 100
    if 10 <= n <= 19:
        words.append(_RU_TEENS[n - 10])
        return words
    if n >= 20:
        words.append(_RU_TENS[n // 10])
        n %= 10
    if n > 0:
        words.append((_RU_UNITS_F if feminine else _RU_UNITS)[n])
    return words


def num_to_words_ru(n: int, feminine: bool = False) -> str:
    if n == 0:
        return "ноль"
    words = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        words += _ru_triple(thousands, feminine=True)
        t = thousands % 100
        u = thousands % 10
        if 11 <= t <= 14:
            words.append("тысяч")
        elif u == 1:
            words.append("тысяча")
        elif 2 <= u <= 4:
            words.append("тысячи")
        else:
            words.append("тысяч")
    if rest:
        words += _ru_triple(rest, feminine=feminine)
    return " ".join(words)


def _kz_triple(n: int) -> list[str]:
    words = []
    if n >= 100:
        h = n // 100
        if h > 1:
            words.append(_KZ_UNITS[h])
        words.append("жүз")
        n %= 100
    if n >= 10:
        words.append(_KZ_TENS[n // 10])
        n %= 10
    if n > 0:
        words.append(_KZ_UNITS[n])
    return words


def num_to_words_kz(n: int) -> str:
    if n == 0:
        return "нөл"
    words = []
    thousands, rest = divmod(n, 1000)
    if thousands:
        if thousands > 1:
            words += _kz_triple(thousands)
        words.append("мың")
    if rest:
        words += _kz_triple(rest)
    return " ".join(words)
