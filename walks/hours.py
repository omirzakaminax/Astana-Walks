"""Small, conservative parser for OpenStreetMap `opening_hours` strings.

Supported: "24/7", "Mo-Su 09:00-22:00", "Mo-Fr 08:00-20:00; Sa,Su 10:00-18:00",
"10:00-22:00" (every day), "Mo-Fr 09:00-13:00,14:00-18:00", "Su off",
overnight ranges like "18:00-02:00".

Anything else (public holidays, months, sunrise, comments, "+") returns status
"unknown" and the raw text is shown to the user. Even a parsed status only reflects
what OSM says - it is never presented as a guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
_DAY_SPEC = re.compile(r"^(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?"
                       r"(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*$")


class UnsupportedFormat(ValueError):
    pass


@dataclass
class HoursStatus:
    status: str  # "open" | "closed" | "unknown" | "not_listed"
    raw: str | None
    minutes_until_close: int | None = None

    def key(self) -> str:
        if self.status == "open":
            return "open_24_7" if self.minutes_until_close is None else "open"
        return self.status

    def to_dict(self) -> dict:
        return {"status": self.status, "key": self.key(), "raw": self.raw,
                "minutes_until_close": self.minutes_until_close}

    def label(self, lang: str = "en") -> str:
        tpl = HOURS_LABELS.get(lang, HOURS_LABELS["en"])[self.key()]
        return tpl.format(raw=self.raw or "", m=self.minutes_until_close)


HOURS_LABELS = {
    "en": {
        "not_listed": "Opening hours are not listed in the source. Check before you go.",
        "unknown": "Hours in OpenStreetMap: \"{raw}\". We could not check whether it is open now.",
        "closed": "Closed now, according to OpenStreetMap (\"{raw}\").",
        "open_24_7": "Open 24/7, according to OpenStreetMap (\"{raw}\"). The data may be out of date.",
        "open": "Open now, according to OpenStreetMap; closes in about {m} min (\"{raw}\"). "
                "The data may be out of date.",
    },
    "ru": {
        "not_listed": "Часы работы в источнике не указаны. Уточните перед визитом.",
        "unknown": "Часы в OpenStreetMap: «{raw}». Проверить, открыто ли сейчас, не удалось.",
        "closed": "По данным OpenStreetMap сейчас закрыто («{raw}»).",
        "open_24_7": "По данным OpenStreetMap работает круглосуточно («{raw}»). Данные могут быть устаревшими.",
        "open": "По данным OpenStreetMap сейчас открыто, закроется примерно через {m} мин («{raw}»). "
                "Данные могут быть устаревшими.",
    },
    "kk": {
        "not_listed": "Жұмыс уақыты дереккөзде көрсетілмеген. Барар алдында нақтылаңыз.",
        "unknown": "OpenStreetMap-тегі жұмыс уақыты: «{raw}». Қазір ашық па, тексеру мүмкін болмады.",
        "closed": "OpenStreetMap деректері бойынша қазір жабық («{raw}»).",
        "open_24_7": "OpenStreetMap деректері бойынша тәулік бойы ашық («{raw}»). Деректер ескірген болуы мүмкін.",
        "open": "OpenStreetMap деректері бойынша қазір ашық, шамамен {m} минуттан кейін жабылады («{raw}»). "
                "Деректер ескірген болуы мүмкін.",
    },
}


def _expand_days(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            i, j = DAYS.index(a), DAYS.index(b)
            idx = i
            while True:
                out.append(idx)
                if idx == j:
                    break
                idx = (idx + 1) % 7
        else:
            out.append(DAYS.index(part))
    return out


def _parse_ranges(spec: str) -> list[tuple[int, int]]:
    ranges = []
    for part in spec.split(","):
        m = _TIME_RANGE.match(part.strip())
        if not m:
            raise UnsupportedFormat(part)
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
            raise UnsupportedFormat(part)
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:  # overnight, e.g. 18:00-02:00
            end += 24 * 60
        ranges.append((start, end))
    return ranges


def parse_week(raw: str) -> dict[int, list[tuple[int, int]]]:
    """Return {weekday: [(start_min, end_min), ...]} with end possibly > 1440 (overnight)."""
    text = raw.strip()
    if text == "24/7":
        return {d: [(0, 24 * 60)] for d in range(7)}
    week: dict[int, list[tuple[int, int]]] = {}
    for rule in [r.strip() for r in text.split(";") if r.strip()]:
        parts = rule.split()
        if len(parts) == 1:
            days, times = list(range(7)), parts[0]
        elif len(parts) == 2 and _DAY_SPEC.match(parts[0]):
            days, times = _expand_days(parts[0]), parts[1]
        else:
            raise UnsupportedFormat(rule)
        if times in ("off", "closed"):
            for d in days:
                week[d] = []
            continue
        ranges = _parse_ranges(times)
        for d in days:
            week[d] = list(ranges)  # later rules override earlier ones (OSM semantics)
    return week


def status_at(raw: str | None, when: datetime) -> HoursStatus:
    if not raw or not raw.strip():
        return HoursStatus("not_listed", None)
    raw = raw.strip()
    try:
        week = parse_week(raw)
    except (UnsupportedFormat, ValueError):
        return HoursStatus("unknown", raw)

    wd = when.weekday()
    now_min = when.hour * 60 + when.minute
    if raw == "24/7":
        return HoursStatus("open", raw, None)
    # Today's ranges
    for start, end in week.get(wd, []):
        if start <= now_min < end:
            return HoursStatus("open", raw, end - now_min)
    # Yesterday's overnight ranges spilling past midnight
    for start, end in week.get((wd - 1) % 7, []):
        if end > 24 * 60 and now_min < end - 24 * 60:
            return HoursStatus("open", raw, end - 24 * 60 - now_min)
    if not week:
        return HoursStatus("unknown", raw)
    # Days not mentioned in the rule are closed under OSM semantics.
    return HoursStatus("closed", raw)


def check_visit(raw: str | None, arrival: datetime, visit_min: int) -> str:
    """Can a visit of `visit_min` minutes starting at `arrival` happen, per OSM hours?

    Returns "ok" (open for the whole visit), "closed" (closed at arrival or closes during
    the visit), or "unknown" (no hours / unsupported format). Unknown is never treated as open.
    """
    st = status_at(raw, arrival)
    if st.status in ("not_listed", "unknown"):
        return "unknown"
    if st.status == "closed":
        return "closed"
    if st.minutes_until_close is not None and st.minutes_until_close < visit_min:
        return "closed"
    return "ok"
