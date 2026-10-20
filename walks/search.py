"""Search the collected places by any of their names (start picker, named places in requests).

Matches the original name, explicit OSM name:xx tags, official/alt/short/old names, names of
merged duplicate records, verified Wikidata labels, reviewed overrides, Latin transliterations,
a sound "skeleton" that ignores spelling differences between scripts, and initials ("AITU").
Only places in our dataset are searched: "not found" does not mean the place does not exist.
"""
from __future__ import annotations

import re
import threading
from difflib import SequenceMatcher

from .names import search_strings
from .translit import skeleton, to_latin

_WORD = re.compile(r"[0-9a-zа-яёәіңғүұқөһ]+", re.IGNORECASE)
# Generic words that must not, on their own, identify a place in free text.
GENERIC = {
    "park", "парк", "саябақ", "саябағы", "cafe", "кафе", "coffee", "кофе", "museum", "музей", "мұражай", "mall",
    "центр", "center", "centre", "орталығы", "театр", "theatre", "мечеть", "mosque", "мешіт", "мешіті",
    "church", "шіркеу", "собор", "square", "площадь", "алаң", "алаңы", "bridge", "мост", "көпір", "көпірі",
    "restaurant", "ресторан", "bar", "бар", "astana", "астана", "the", "and", "near", "city", "сити", "плаза",
    "plaza", "fountain", "фонтан", "monument", "памятник", "ескерткіш", "university", "университет", "school",
    "школа", "library", "библиотека", "кітапхана", "gallery", "галерея", "арт", "art", "ресторан", "house",
    "дом", "үй", "мега", "mega", "kids", "дети", "балалар", "sport", "спорт", "fitness", "фитнес", "boom", "бум",
}


def norm(s: str) -> str:
    return " ".join(_WORD.findall((s or "").lower().replace("ё", "е")))


def initials(s: str) -> str:
    """'Astana IT University' -> 'aitu' (short upper-case words such as 'IT' are kept whole)."""
    raw = re.findall(r"[0-9A-Za-zА-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]+", to_latin(s or ""))
    words = [w for w in raw if w.lower() not in ("of", "the", "and", "i", "и")]
    if len(words) < 2:
        return ""
    return "".join(w.lower() if (w.isupper() and len(w) <= 3) else w[0].lower() for w in words)


class Index:
    def __init__(self, pois: list[dict]):
        self.entries = []  # (poi, normalized string, skeleton, initials)
        for p in pois:
            if p.get("name_is_generated"):
                continue
            for s in search_strings(p):
                n = norm(s)
                if n:
                    self.entries.append((p, n, skeleton(s), initials(s)))

    def search(self, query: str, limit: int = 12, fuzzy: bool = True) -> list[tuple[dict, int]]:
        q = norm(query)
        if not q:
            return []
        ql, qs = norm(to_latin(query)), skeleton(query)
        best: dict[str, tuple[dict, int]] = {}
        for p, n, sk, ini in self.entries:
            score = 0
            if n == q or n == ql:
                score = 100
            elif n.startswith(q) or n.startswith(ql):
                score = 85
            elif len(q) >= 2 and ini and q.replace(" ", "") == ini:
                score = 80
            elif sk and len(qs) >= 3 and sk == qs:
                score = 75
            elif sk and len(qs) >= 6 and " " in q and sk.startswith(qs):
                # several words that sound like the START of the name, across spellings:
                # "Хазірет Сұлтан" -> "Хазрет Султан мешіті"
                score = 76
            else:
                toks = q.split()
                words = n.split()
                if all(any(w.startswith(t) for w in words) for t in toks) and len(q) >= 3:
                    score = 65
                elif fuzzy and len(qs) >= 4 and sk and SequenceMatcher(None, qs, sk).ratio() >= 0.8:
                    score = int(55 * SequenceMatcher(None, qs, sk).ratio())
            if score and score > best.get(p["id"], (None, 0))[1]:
                best[p["id"]] = (p, score)
        ranked = sorted(best.values(), key=lambda x: (-x[1], not x[0].get("notable"), x[0]["name"]))
        return ranked[:limit]


_cache: dict = {"key": None, "index": None}
_lock = threading.Lock()


def index_for(ds) -> Index:
    """One index per loaded dataset object (rebuilt when the dataset file changes)."""
    with _lock:
        if _cache["key"] is not ds:
            _cache["index"], _cache["key"] = Index(ds.pois), ds
        return _cache["index"]


# ------------------------------------------------------------------ places named in free text
# Only clear "I am here" words. Short ambiguous ones ("у", "в", "at", "by") caused false questions
# ("у нас час" = "we have an hour").
LOCATION_CUES = {
    "en": ["near", "from", "around", "next to", "close to", "starting at", "i am at", "i m at", "i'm at", "start at"],
    "ru": ["рядом с", "возле", "около", "от", "недалеко от", "я у", "я возле", "я около", "начать от", "стою у"],
    "kk": ["маңында", "жанында", "қасында", "тұрмын", "жақын", "маңынан", "жанынан"],
}


_ENDINGS = sorted(["тың", "тің", "дың", "дің", "ның", "нің", "ға", "ге", "қа", "ке", "на", "не", "да", "де", "та",
                   "те", "нан", "нен", "дан", "ден", "тан", "тен", "мен", "пен", "бен", "ом", "ем", "ой", "ей",
                   "ым", "ах", "ях", "ами", "ями", "а", "я", "у", "ю", "е", "ы", "и",
                   # Kazakh possessive/accusative: "мешітін", "саябағын", "орталығына"
                   "ін", "ын", "ні", "ны", "ді", "ды", "ті", "ты", "сі", "сы", "ің", "ың", "іне", "ына", "і", "н"], key=len, reverse=True)


def strip_case(word: str) -> list[str]:
    """Possible stems of a Kazakh/Russian word with a case ending ("Байтерека" -> "Байтерек")."""
    out = []
    for e in _ENDINGS:
        if word.endswith(e) and len(word) - len(e) >= 4:
            out.append(word[: -len(e)])
    return out[:4]


def find_mentions(ds, text: str) -> list[dict]:
    """Places whose name appears in the request. Returns [{poi, score, phrase, cue}] (best first).

    Only distinctive names count: a single generic word ("park", "кафе") never identifies a place.
    `cue` is True when a location word ("near", "рядом с", "маңында") is next to the name,
    i.e. the user is describing where they ARE rather than where they want to go.
    """
    tokens = norm(text).split()
    if not tokens:
        return []
    idx = index_for(ds)
    found: dict[str, dict] = {}
    for size in (4, 3, 2, 1):
        for i in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[i:i + size])
            if all(t in GENERIC or len(t) < 3 for t in phrase.split()):
                continue
            if size == 1 and len(phrase) < 5:
                continue
            hits = {}
            for variant in [phrase] + [" ".join(phrase.split()[:-1] + [st]) for st in strip_case(phrase.split()[-1])]:
                for poi, sc in idx.search(variant, limit=5, fuzzy=False):  # fuzzy scores < 75 anyway
                    if sc > hits.get(poi["id"], (None, 0))[1]:
                        hits[poi["id"]] = (poi, sc)
            for poi, score in hits.values():
                if score < 75 or (score in (85, 76) and size == 1):
                    continue  # one word that is only the START of a longer name is too weak
                before = " ".join(tokens[max(0, i - 3):i])
                after = " ".join(tokens[i + size:i + size + 2])
                cue = any(f" {c} " in f" {before} " for lang in ("en", "ru") for c in LOCATION_CUES[lang]) or \
                    any(after.startswith(c) or f" {c}" in f" {after}" for c in LOCATION_CUES["kk"])
                cur = found.get(poi["id"])
                if not cur or score > cur["score"] or len(phrase) > len(cur["phrase"]):
                    found[poi["id"]] = {"poi": poi, "score": score, "phrase": phrase, "cue": bool(cue)}
        if found:
            break  # the longest matching phrase wins; do not add sub-phrase matches
    return _one_per_place(sorted(found.values(), key=lambda m: -m["score"]))


def _one_per_place(ms: list[dict]) -> list[dict]:
    """Records with the same phrase within 600 m are one place for the user (a monument, its
    square and its visitor centre): keep the richest record (linked to Wikidata, more tags)."""
    from .geo import haversine_m
    out: list[dict] = []
    for m in sorted(ms, key=lambda m: (-m["score"], not m["poi"].get("notable"), -len(m["poi"].get("osm_tags") or {}))):
        if any(o["phrase"] == m["phrase"] and haversine_m(o["poi"]["lat"], o["poi"]["lon"], m["poi"]["lat"], m["poi"]["lon"]) <= 600
               for o in out):
            continue
        out.append(m)
    return out
