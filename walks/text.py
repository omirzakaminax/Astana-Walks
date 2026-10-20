"""Practical Kazakh / Russian / English query understanding (no ML, fully transparent).

* tokenize()           – lowercase word tokens, ё -> е
* detect_language()    – 'kk' if Kazakh-specific letters, 'ru' if other Cyrillic, else 'en'
* detect_intents()     – keyword stems -> intents -> internal categories
* parse_minutes()      – "45 минут", "2 сағат", "1-2 hours", "полчаса" -> minutes
* detect_unsupported() – things our dataset cannot confirm (sockets, quietness...)
"""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-zа-яәіңғүұқөһ0-9]+", re.IGNORECASE)
CYRILLIC_RE = re.compile(r"[а-яёәіңғүұқөһ]", re.IGNORECASE)
KAZAKH_RE = re.compile(r"[әіңғүұқөһ]", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower().replace("ё", "е"))


def detect_language(text: str) -> str:
    if KAZAKH_RE.search(text or ""):
        return "kk"
    return "ru" if CYRILLIC_RE.search(text or "") else "en"


def _matches(token: str, stem: str) -> bool:
    # Short stems must match exactly to avoid false positives ("art" vs "artificial").
    if len(stem) <= 3:
        return token == stem
    return token.startswith(stem)


# intent -> (keyword stems in en/ru/kk, categories)
INTENTS: dict[str, tuple[list[str], list[str]]] = {
    "coffee": (
        ["coffee", "cafe", "cafes", "espresso", "latte",
         "кофе", "кофей", "кафе", "капучин", "латте",
         "кофехана"],
        ["cafe"],
    ),
    "food": (
        ["eat", "food", "lunch", "dinner", "breakfast", "restaurant", "hungry",
         "поесть", "еда", "покуш", "обед", "ужин", "завтрак", "ресторан", "перекус", "голод",
         "тамақ", "түскі", "таңғы", "мейрамхан", "асхана", "жеуге", "жегім"],
        ["restaurant", "fast_food", "cafe"],
    ),
    "walk": (
        ["walk", "walking", "stroll", "park", "parks", "outdoor", "outdoors",
         "прогул", "погуля", "гулять", "пройт", "парк", "сквер", "свеж",
         "серуен", "қыдыр", "саябақ", "гүлзар", "жаяу"],
        ["park", "viewpoint", "attraction", "artwork", "fountain"],
    ),
    "kids": (
        ["child", "children", "kid", "kids", "family", "son", "daughter", "toddler", "playground",
         "ребен", "дет", "сын", "доч", "семь", "малыш", "площадк",
         "бала", "отбасы", "сәби", "немере"],
        ["playground", "park", "museum", "zoo", "theme_park", "ice_cream"],
    ),
    "culture": (
        ["museum", "museums", "gallery", "art", "exhibition", "culture", "theatre", "theater",
         "музе", "галере", "искусств", "выставк", "культур", "театр",
         "мұражай", "көрме", "өнер", "мәдени"],
        ["museum", "gallery", "arts_centre", "artwork", "theatre"],
    ),
    "views": (
        ["view", "views", "viewpoint", "photo", "photos", "panorama",
         "вид", "виды", "смотров", "фото", "панорам",
         "көрініс", "шолу", "сурет"],
        ["viewpoint", "attraction", "artwork"],
    ),
    "sights": (
        ["sightseeing", "tourist", "landmark", "landmarks", "attraction", "unusual", "interesting", "sights",
         "достопримечат", "турист", "необычн", "интересн", "посмотреть",
         "көрікті", "қызық", "көруге", "таңғаж",
         "must", "famous", "main", "главн", "обязательн", "знаменит", "известн", "атақты", "міндетті", "әйгілі", "басты"],
        ["attraction", "viewpoint", "museum", "artwork", "gallery"],
    ),
    "shopping": (
        ["mall", "shopping", "shop", "shops",
         "торгов", "трц", "шопинг", "магазин",
         "сауда", "дүкен"],
        ["mall"],
    ),
    "sport": (
        ["sport", "sports", "gym", "fitness", "workout",
         "спорт", "фитнес", "трениров",
         "жаттығу"],
        ["sports"],
    ),
    "movie": (
        ["cinema", "movie", "movies", "film",
         "кино", "фильм"],
        ["cinema"],
    ),
    "sweet": (
        ["ice", "cream", "dessert", "sweet",
         "морожен", "десерт", "сладк",
         "балмұздақ", "тәтті"],
        ["ice_cream", "cafe"],
    ),
    "indoor": (
        ["indoor", "indoors", "inside", "warm", "warmer", "freezing", "cold",
         "тепл", "тёпл", "погреть", "согреть", "внутри", "помещен", "холодн", "мороз",
         "жылы", "жылын", "суық", "ішінде", "жабық"],
        ["mall", "cafe", "museum", "gallery", "arts_centre", "library", "cinema"],
    ),
    "study": (
        ["library", "read", "study", "work", "laptop",
         "библиотек", "почитать", "учеб", "поработ", "ноутбук",
         "кітапхана", "оқу", "сабақ", "жұмыс"],
        ["library", "cafe"],
    ),
}

INTENT_LABELS: dict[str, dict[str, str]] = {
    "coffee": {"en": "Coffee", "ru": "Кофе", "kk": "Кофе"},
    "food": {"en": "Food", "ru": "Еда", "kk": "Тамақ"},
    "walk": {"en": "Walk and parks", "ru": "Прогулка и парки", "kk": "Серуен және саябақтар"},
    "kids": {"en": "With kids", "ru": "С детьми", "kk": "Балалармен"},
    "culture": {"en": "Culture and art", "ru": "Культура и искусство", "kk": "Мәдениет және өнер"},
    "views": {"en": "Views and photos", "ru": "Виды и фото", "kk": "Көріністер мен суреттер"},
    "sights": {"en": "Sights", "ru": "Достопримечательности", "kk": "Көрікті жерлер"},
    "shopping": {"en": "Shopping", "ru": "Покупки", "kk": "Сауда"},
    "sport": {"en": "Sport", "ru": "Спорт", "kk": "Спорт"},
    "movie": {"en": "Cinema", "ru": "Кино", "kk": "Кино"},
    "sweet": {"en": "Dessert", "ru": "Десерт", "kk": "Десерт"},
    "study": {"en": "Study or work", "ru": "Учёба или работа", "kk": "Оқу немесе жұмыс"},
    "indoor": {"en": "Somewhere warm indoors", "ru": "В тепле, в помещении", "kk": "Жылы, жабық жерде"},
}

# Things a user may ask for that the OSM dataset usually cannot confirm.
# key -> (stems, OSM tag that *can* confirm it if present)
UNSUPPORTED: dict[str, tuple[list[str], str | None]] = {
    "sockets": (["socket", "sockets", "outlet", "outlets", "charge", "charging", "power",
                 "розетк", "заряд", "қуаттау"], None),
    "quiet": (["quiet", "calm", "silent", "peaceful", "тихо", "тихи", "тиха", "тиху", "спокойн",
               "тыныш"], None),
    "price": (["cheap", "budget", "price", "prices", "inexpensive", "affordable",
               "дешев", "недорог", "бюджет", "цен", "арзан", "баға"], None),
    "rating": (["rating", "best", "popular", "review", "reviews", "top",
                "рейтинг", "лучш", "популярн", "отзыв", "үздік", "танымал", "пікір"], None),
    "events": (["event", "events", "concert", "party", "festival",
                "мероприят", "вечеринк", "афиш", "событ", "концерт", "фестивал", "шара"], None),
    "crowds": (["crowded", "busy", "людн", "народ", "адамсыз"], None),
    "wifi": (["wifi", "wi", "internet", "интернет", "вайфай"], "internet_access"),
    "wheelchair": (["wheelchair", "accessible", "accessibility", "stroller",
                    "коляск", "инвалид", "мүгедек", "арбамен"], "wheelchair"),
}

UNSUPPORTED["rooftop"] = (["rooftop", "rooftops", "roof", "крыш", "руфтоп"], None)

UNSUPPORTED_LABELS: dict[str, dict[str, str]] = {
    "sockets": {"en": "power sockets", "ru": "розетки", "kk": "розеткалар"},
    "quiet": {"en": "quietness", "ru": "тишина", "kk": "тыныштық"},
    "price": {"en": "prices", "ru": "цены", "kk": "бағалар"},
    "rating": {"en": "ratings and popularity", "ru": "рейтинг и популярность", "kk": "рейтинг пен танымалдық"},
    "events": {"en": "current events", "ru": "текущие мероприятия", "kk": "ағымдағы іс-шаралар"},
    "crowds": {"en": "how crowded it is", "ru": "загруженность", "kk": "адам көптігі"},
    "wifi": {"en": "Wi-Fi", "ru": "Wi-Fi", "kk": "Wi-Fi"},
    "wheelchair": {"en": "wheelchair access", "ru": "доступность для колясок", "kk": "арбамен кіру мүмкіндігі"},
    "rooftop": {"en": "rooftop access", "ru": "доступ на крышу", "kk": "шатырға шығу мүмкіндігі"},
}

NIGHT_STEMS = ["night", "late", "tonight", "ночь", "ночн", "поздн", "вечер", "түнде", "түнгі", "кешке", "кеште"]


# ------------------------------------------------------------------ negation ("no cafes", "не музей")
NEG_BEFORE = {"not", "no", "without", "except", "nor", "avoid", "skip", "не", "без", "кроме", "никаких", "ни"}
NEG_PHRASES_BEFORE = ["don t want", "do not want", "dont want", "not a", "not an", "no more", "только не",
                      "не хочу", "не надо", "не нужно", "не нужен", "не нужна"]
NEG_AFTER = ["емес", "керек емес", "қажет емес", "не надо", "не нужно", "не хочу", "не нужен", "не нужна"]
KK_WITHOUT = ("сыз", "сіз")  # Kazakh "-сыз/-сіз" = without: "кафесіз" = without a cafe

# Category words that a negation can apply to (in addition to the intent stems).
CATEGORY_WORDS: dict[str, list[str]] = {
    "cafe": ["cafe", "cafes", "coffee", "кафе", "кофе", "кофейн", "кофехана"],
    "restaurant": ["restaurant", "ресторан", "мейрамхан"],
    "fast_food": ["fast", "фастфуд", "fastfood"],
    "museum": ["museum", "музе", "мұражай"],
    "gallery": ["gallery", "галере"],
    "park": ["park", "парк", "саябақ", "сквер"],
    "playground": ["playground", "площадк", "алаң"],
    "mall": ["mall", "malls", "торгов", "трц", "молл", "сауда"],
    "cinema": ["cinema", "movie", "кино"],
    "theatre": ["theatre", "theater", "театр"],
    "artwork": ["monument", "monuments", "памятник", "ескерткіш", "статуя", "sculpture"],
    "worship": ["mosque", "church", "мечет", "церк", "храм", "собор", "мешіт", "шіркеу"],
    "library": ["library", "библиотек", "кітапхана"],
    "sports": ["gym", "fitness", "спортзал", "фитнес"],
    "ice_cream": ["ice", "морожен", "балмұздақ"],
    "attraction": ["attraction", "attractions"],
}


def _token_categories(token: str) -> list[str]:
    out = []
    for cat, stems in CATEGORY_WORDS.items():
        if any(_matches(token, s) for s in stems):
            out.append(cat)
    return out


def detect_negations(text: str) -> tuple[list[str], set[int]]:
    """(excluded categories, indexes of negated tokens). Handles "no cafes", "not a museum",
    "without malls", "не музей", "без кафе", "кроме ТРЦ", "мұражай емес", "кафесіз"."""
    tokens = tokenize(text)
    negated: set[int] = set()
    for i, t in enumerate(tokens):
        prev = " ".join(tokens[max(0, i - 3):i])
        pre = (i > 0 and tokens[i - 1] in NEG_BEFORE) or (i > 1 and tokens[i - 2] in NEG_BEFORE and
                                                         tokens[i - 1] in ("a", "an", "any", "the", "to", "в", "на"))
        pre = pre or any(f" {p} " in f" {prev} " and prev.endswith(p.split()[-1]) for p in NEG_PHRASES_BEFORE)
        post = any(" ".join(tokens[i + 1:i + 1 + len(p.split())]) == p for p in NEG_AFTER)
        kk_without = any(t.endswith(sfx) and _token_categories(t[: -len(sfx)]) for sfx in KK_WITHOUT)
        if (pre or post or kk_without) and (_token_categories(t) or kk_without):
            negated.add(i)
    cats: list[str] = []
    for i in sorted(negated):
        t = tokens[i]
        for sfx in KK_WITHOUT:
            if t.endswith(sfx) and _token_categories(t[: -len(sfx)]):
                t = t[: -len(sfx)]
        for c in _token_categories(t):
            if c not in cats:
                cats.append(c)
    return cats, negated


FLIGHT_STEMS = ["flight", "airport", "plane", "рейс", "самолет", "аэропорт", "вылет", "ұшақ", "әуежай", "ұшу"]


def mentions_flight(text: str) -> bool:
    return any(_matches(t, s) for t in tokenize(text) for s in FLIGHT_STEMS)


# "Somewhere warm / indoors" — a real wish in Astana winters, distinct from "walk".
SEQUENCE_WORDS = ["then", "after", "afterwards", "followed", "потом", "затем", "после", "кейін", "соң", "соңынан"]


def mentions_sequence(text: str) -> bool:
    return any(t in SEQUENCE_WORDS for t in tokenize(text))


def intents_in_order(text: str) -> list[str]:
    """Intents in the order they are MENTIONED ("coffee, then a walk" -> coffee, walk)."""
    tokens = tokenize(text)
    _cats, negated = detect_negations(text)
    found: list[str] = []
    first: dict[str, int] = {}
    for name, (stems, _c) in INTENTS.items():
        for i, t in enumerate(tokens):
            if i not in negated and any(_matches(t, s) for s in stems):
                first[name] = i
                break
    return sorted(first, key=lambda n: first[n])


def detect_intents(text: str, extra_intents: list[str] | None = None) -> list[str]:
    """Detected intents in a stable order. Negated words ("no cafes") never add an intent."""
    mentioned = set(intents_in_order(text))
    found: list[str] = [n for n in INTENTS if n in mentioned]
    for name in extra_intents or []:
        if name in INTENTS and name not in found:
            found.append(name)
    return found


def categories_for(intents: list[str]) -> list[str]:
    cats: list[str] = []
    for name in intents:
        for c in INTENTS[name][1]:
            if c not in cats:
                cats.append(c)
    return cats


def expansion_terms(intents: list[str]) -> list[str]:
    """Extra query terms so BM25 can match category words in all three languages."""
    terms: list[str] = []
    for name in intents:
        terms.extend(INTENTS[name][1])
        terms.extend(s for s in INTENTS[name][0] if len(s) > 3)
    return terms


def detect_unsupported(text: str) -> list[str]:
    tokens = tokenize(text)
    hits = []
    for key, (stems, _tag) in UNSUPPORTED.items():
        if any(_matches(t, s) for t in tokens for s in stems):
            hits.append(key)
    return hits


def mentions_night(text: str) -> bool:
    tokens = tokenize(text)
    return any(_matches(t, s) for t in tokens for s in NIGHT_STEMS)


_UNIT_MIN = r"(?:minutes?|mins?|min|мин(?:ут[аы]?|\.)?|минут\w*)"
_UNIT_H = r"(?:hours?|hrs?|h|час(?:а|ов)?|ч|сағат\w*)"
_NUM = r"(\d+(?:[.,]\d+)?)"


def parse_minutes(text: str) -> int | None:
    """Extract a time budget from free text. Uses the upper bound of a range.

    Returns None when no time is mentioned.
    """
    t = (text or "").lower().replace("ё", "е")
    candidates: list[float] = []
    for m in re.finditer(_NUM + r"\s*(?:[-–—]|to|до)\s*" + _NUM + r"\s*" + _UNIT_H + r"\b", t):
        candidates.append(float(m.group(2).replace(",", ".")) * 60)
    for m in re.finditer(_NUM + r"\s*(?:[-–—]|to|до)\s*" + _NUM + r"\s*" + _UNIT_MIN, t):
        candidates.append(float(m.group(2).replace(",", ".")))
    if not candidates:
        for m in re.finditer(_NUM + r"\s*" + _UNIT_H + r"\b", t):
            candidates.append(float(m.group(1).replace(",", ".")) * 60)
        for m in re.finditer(_NUM + r"\s*" + _UNIT_MIN, t):
            candidates.append(float(m.group(1).replace(",", ".")))
    if not candidates:
        if re.search(r"полтора час|бір жарым сағат|one and a half hour", t):
            return 90
        if re.search(r"\bhalf an hour\b|полчаса|жарты сағат", t):
            return 30
        if re.search(r"\b(an|one) hour\b|\bчас\b|\bчасик|бір сағат|\bсағат\b", t):
            return 60
        return None
    minutes = int(round(max(candidates)))
    return minutes if minutes > 0 else None


NOTABLE_STEMS = ["must", "famous", "landmark", "main", "главн", "обязательн", "знаменит", "известн",
                 "достопримечат", "атақты", "міндетті", "әйгілі", "басты", "көрікті"]


def wants_notable(text: str) -> bool:
    tokens = tokenize(text)
    return any(_matches(t, s) for t in tokens for s in NOTABLE_STEMS)
