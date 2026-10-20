"""Check generated text against the evidence for ONE place, clause by clause.

Why clause level: "Free entry and a quiet cafe. Sockets are unknown." contains one honest
statement ("sockets are unknown") and two unsupported claims. An "unknown" anywhere in the text
must not excuse claims elsewhere, so each clause is judged on its own.

Each claim type maps to the evidence FIELDS that could support it (not to words that happen to
appear somewhere in the serialized evidence):

  price / free entry  -> extra_osm_tags.fee ("no" supports "free") or extra_osm_tags.charge
  wifi                -> extra_osm_tags.internet_access in (wlan, yes, wifi)
  wheelchair access   -> extra_osm_tags.wheelchair in (yes, limited)
  outdoor seating     -> extra_osm_tags.outdoor_seating == yes
  open now            -> the code's opening-hours status for this place is "open"
  ratings, sockets, quietness, crowds, live events -> never in our data: always unsupported
  dates/years         -> the year must appear in the place's description/Wikipedia text

Unsupported sentences are REMOVED before the text is shown (the card says what was removed);
a warning under a false claim is not enough. Automatic checking is limited: it catches the claim
types above in three languages, not every possible invented fact.
"""
from __future__ import annotations

import re

HONEST_UNKNOWN = re.compile(r"unknown|not known|no data|not confirm|unclear|can't confirm|cannot confirm|"
                            r"неизвест|нет данных|не указан|не подтвержд|неясно|"
                            r"белгісіз|дерек жоқ|көрсетілмеген|расталмаған")

CLAIMS: dict[str, list[str]] = {
    "free": ["free entry", "free admission", "free of charge", "admission is free", "entry is free", "бесплатн",
             "тегін"],
    "prices": ["₸", "tenge", "тенге", "теңге", "cheap", "inexpensive", "affordable", "дешев", "недорог", "арзан",
               "price", "цена", "цены", "баға"],
    "ratings": ["rating", "рейтинг", "rated", "stars", "звезд", "жұлдыз", "best in", "лучш", "үздік", "popular",
                "популярн", "танымал", "top-rated"],
    "sockets": ["socket", "outlet", "розетк"],
    "quiet": ["quiet", "calm", "peaceful", "тих", "спокойн", "тыныш"],
    "crowds": ["not crowded", "crowded", "людн", "многолюдн", "адам көп", "адам аз"],
    "events": ["exhibition is on", "concert tonight", "event today", "идет выставка", "идёт выставка",
               "мероприятие сегодня", "бүгін концерт", "көрме өтіп жатыр", "festival"],
    "wifi": ["wi-fi", "wifi", "вай-фай", "интернет"],
    "wheelchair": ["wheelchair", "step-free", "accessible for", "для колясок", "арбамен"],
    "outdoor_seating": ["terrace", "outdoor seating", "веранд", "летник", "террас"],
    "rooftop": ["rooftop", "on the roof", "на крыше", "руфтоп"],
    "interactive": ["interactive", "hands-on", "интерактив"],
}
OPEN_NOW = ["open now", "is open", "открыто сейчас", "сейчас открыто", "работает сейчас", "открыт сейчас",
            "қазір ашық"]
YEAR = re.compile(r"\b(1[89]\d\d|20[0-3]\d)\b")
_SENT = re.compile(r"(?<=[.!?;])\s+")
_CLAUSE = re.compile(r",|;|\bbut\b|\bhowever\b|\bно\b|\bоднако\b|\bбірақ\b|\bалайда\b", re.IGNORECASE)


def _supported(claim: str, ev: dict) -> bool:
    tags = ev.get("extra_osm_tags") or {}
    if claim == "free":
        return tags.get("fee") == "no"
    if claim == "prices":
        return bool(tags.get("charge")) or tags.get("fee") in ("yes", "no")
    if claim == "wifi":
        return tags.get("internet_access") in ("wlan", "yes", "wifi")
    if claim == "wheelchair":
        return tags.get("wheelchair") in ("yes", "limited")
    if claim == "outdoor_seating":
        return tags.get("outdoor_seating") == "yes"
    if claim == "interactive":   # only if the place's own description/Wikipedia text says so
        txt = " ".join(str(ev.get(k) or "") for k in ("description", "about_from_wikipedia")).lower()
        return any(w in txt for w in ("interactive", "интерактив"))
    return False  # ratings, sockets, quietness, crowds, events: never in our data


def clause_claims(clause: str, ev: dict, hours_status: str | None) -> list[str]:
    c = clause.lower()
    if HONEST_UNKNOWN.search(c):
        return []  # "sockets are unknown" in THIS clause is an honest statement
    out = []
    for claim, phrases in CLAIMS.items():
        # "no Wi-Fi" is a claim too: missing data means unknown, not "no".
        if any(p in c for p in phrases) and not _supported(claim, ev):
            out.append(claim)
    if hours_status is not None and hours_status != "open" and any(p in c for p in OPEN_NOW):
        out.append("open_now")
    evidence_text = " ".join(str(ev.get(k) or "") for k in ("description", "about_from_wikipedia", "name"))
    for y in YEAR.findall(clause):
        if y not in evidence_text:
            out.append("dates")
            break
    return out


def check(text: str, ev: dict, hours_status: str | None = None) -> tuple[str, list[str]]:
    """(text with unsupported sentences removed, claim types removed). Order of claims is stable."""
    text = (text or "").strip()
    if not text:
        return "", []
    kept, removed = [], []
    for sent in _SENT.split(text):
        flags = []
        for clause in _CLAUSE.split(sent):
            flags += clause_claims(clause, ev, hours_status)
        if flags:
            removed += [f for f in flags if f not in removed]
        else:
            kept.append(sent)
    return " ".join(kept).strip(), removed


def flag_only(text: str, ev: dict, hours_status: str | None = None) -> list[str]:
    """Claim types found in text (nothing removed) — used by the evaluation script."""
    return check(text, ev, hours_status)[1]


def script_matches(text: str, lang: str) -> bool:
    """Rough language check by script: kk/ru answers should be mostly Cyrillic, en mostly Latin.
    (Place names may be in either script, so only clear mismatches count.)"""
    letters = re.findall(r"[A-Za-zА-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]", text or "")
    if len(letters) < 20:
        return True
    cyr = sum(1 for ch in letters if re.match(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]", ch)) / len(letters)
    return cyr >= 0.5 if lang in ("ru", "kk") else cyr <= 0.5
