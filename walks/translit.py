"""Kazakh/Russian Cyrillic -> Latin transliteration (for display and duplicate matching).

Used only when a place has no English name in OpenStreetMap. The UI marks transliterated
names and keeps the original name visible.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_MAP = {
    "а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m", "н": "n",
    "ң": "ng", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u",
    "ү": "u", "ф": "f", "х": "kh", "һ": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "і": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_CYR = re.compile(r"[а-яёәіңғүұқөһ]", re.IGNORECASE)


# Words with an established Latin spelling (brands, landmarks, common place words).
# Applied to whole words before letter-by-letter transliteration.
KNOWN_WORDS = {
    "экспо": "EXPO", "expo": "EXPO", "астана": "Astana", "байтерек": "Baiterek", "бәйтерек": "Baiterek",
    "хан": "Khan", "шатыр": "Shatyr", "нұр": "Nur", "нур": "Nur", "әлем": "Alem", "алем": "Alem",
    "мега": "Mega", "силк": "Silk", "вей": "Way", "молл": "Mall", "плаза": "Plaza", "сити": "City",
    "парк": "Park", "центр": "Centre", "орталығы": "Centre", "трц": "Mall", "тц": "Mall",
    "кафе": "Cafe", "кофе": "Coffee", "ресторан": "Restaurant", "музей": "Museum", "мұражайы": "Museum",
    "театр": "Theatre", "мечеть": "Mosque", "мешіті": "Mosque", "собор": "Cathedral", "арена": "Arena",
    "университет": "University", "площадь": "Square", "бульвар": "Boulevard", "аллея": "Alley",
    "бум": "Boom", "бар": "Bar", "гранд": "Grand", "арт": "Art", "лаунж": "Lounge", "хаус": "House",
    "абу": "Abu", "даби": "Dhabi", "керуен": "Keruen", "хазрет": "Hazret", "султан": "Sultan",
}
_WORD = re.compile(r"[A-Za-zА-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]+")


def has_cyrillic(text: str) -> bool:
    return bool(_CYR.search(text or ""))


def to_latin(text: str) -> str:
    text = _WORD.sub(lambda m: KNOWN_WORDS.get(m.group(0).lower(), m.group(0)), text or "")
    out = []
    for ch in text or "":
        low = ch.lower()
        if low in _MAP:
            lat = _MAP[low]
            out.append(lat.capitalize() if ch != low and lat else lat)
        else:
            out.append(ch)
    return "".join(out)


def skeleton(name: str) -> str:
    """Script-independent sound skeleton: 'Мега Силк Вей' and 'Mega Silk Way' -> same string."""
    s = to_latin(name or "").lower()
    s = (s.replace("kh", "h").replace("sh", "s").replace("ch", "9").replace("ts", "9").replace("c", "k")
          .replace("9", "c").replace("w", "v").replace("ph", "f").replace("x", "ks").replace("q", "k")
          .replace("ng", "n"))
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"[aeiouyj]", "", s)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def same_name(a: str, b: str, threshold: float = 0.84) -> bool:
    # Names that differ in their numbers are different places ("School 5" vs "School 7").
    if re.findall(r"\d+", a or "") != re.findall(r"\d+", b or ""):
        return False
    sa, sb = skeleton(a), skeleton(b)
    if len(sa) < 3 or len(sb) < 3:
        return (a or "").strip().lower() == (b or "").strip().lower()
    if sa == sb:
        return True
    return SequenceMatcher(None, sa, sb).ratio() >= threshold
