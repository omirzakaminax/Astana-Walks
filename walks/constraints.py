"""Resolve and validate all user constraints for one request (server-side).

PRECEDENCE (documented, applied in this order):
  1. Base time: the duration written in the request text ("2 hours") if any, otherwise
     the time setting. In group mode the base is the shortest participant's time, and a
     duration in the text can only shorten it further.
  2. Hard caps that can only shorten, never lengthen, the plan:
       * group: the shortest available time of any participant;
       * deadline ("back by"): minutes until the deadline minus the safety buffer.
     effective_time = min(base, all active caps).
  3. Pace: the slowest pace of any participant (solo: the chosen pace).
  4. Return: a deadline always implies returning to the start point.
  5. Outdoor limit (if set) is a hard cap on estimated outdoor minutes; it is never relaxed
     automatically.
  6. Negations in the text ("no cafes") and the source-based filters (known opening hours,
     OSM wheelchair tag) are hard filters. They change only when the user explicitly clicks a
     suggested change; the response shows what would change before anything is re-run.
  7. An active walk ("I'm here") replans from the current position with the REMAINING time
     (the deadline, if any, is re-computed from now) and returns to the ORIGINAL start point.
Every value is validated here; frontend validation is only a convenience.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import config
from .geo import PACES
from .text import INTENTS, parse_minutes

PACE_ORDER = ["leisurely", "normal", "brisk"]
MAX_MINUTES = 12 * 60
MIN_MINUTES = 5


class ConstraintError(ValueError):
    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params


@dataclass
class Participant:
    interests: list[str]
    minutes: int
    pace: str


@dataclass
class Constraints:
    now: datetime
    budget_min: int
    budget_source: str                 # "text" | "setting" | "group" | "deadline"
    limits: dict                       # each proposed maximum, for transparency
    pace: str
    speed: float
    return_to_start: bool
    interests: list[str]
    deadline: dict | None = None       # {at, buffer_min, minutes_left, cap_min}
    outdoor_max: int | None = None
    outdoor_strict: bool = False
    participants: list[Participant] = field(default_factory=list)
    exclude: dict = field(default_factory=lambda: {"visited": [], "unavailable": [], "other": []})
    filters: dict = field(default_factory=lambda: {"known_hours": False, "wheelchair": False})
    broaden: bool = False

    def to_dict(self) -> dict:
        return {
            "now": self.now.strftime("%Y-%m-%dT%H:%M"), "weekday": self.now.weekday(),
            "budget_min": self.budget_min, "budget_source": self.budget_source, "limits": self.limits,
            "pace": self.pace, "speed_m_per_min": self.speed, "detour_factor": config.ROUTE_DETOUR_FACTOR,
            "return_to_start": self.return_to_start, "deadline": self.deadline,
            "outdoor": {"max_min": self.outdoor_max, "strict": self.outdoor_strict},
            "group": [{"interests": p.interests, "minutes": p.minutes, "pace": p.pace} for p in self.participants],
            "filters": self.filters, "broaden": self.broaden,
        }

    @property
    def excluded_ids(self) -> set[str]:
        return set(self.exclude["visited"]) | set(self.exclude["unavailable"]) | set(self.exclude["other"])


def _int(value, code: str, lo: int, hi: int, default=None) -> int:
    if value is None or value == "":
        if default is not None:
            return default
        raise ConstraintError(code, min=lo, max=hi)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ConstraintError(code, min=lo, max=hi) from None
    if math.isnan(v) or not lo <= v <= hi:
        raise ConstraintError(code, min=lo, max=hi)
    return int(round(v))


def _interests(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConstraintError("bad_interests")
    out = []
    for i in raw[:12]:
        if not isinstance(i, str) or i not in INTENTS:
            raise ConstraintError("bad_interests")
        if i not in out:
            out.append(i)
    return out


def _pace(raw) -> str:
    if raw in (None, ""):
        return "normal"
    if raw not in PACES:
        raise ConstraintError("bad_pace")
    return raw


def _ids(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 300:
        raise ConstraintError("bad_exclusions")
    out = []
    for x in raw:
        if not isinstance(x, str) or len(x) > 80:
            raise ConstraintError("bad_exclusions")
        out.append(x)
    return out


def parse_deadline(raw: dict, now: datetime) -> dict:
    at_s = raw.get("at")
    if not isinstance(at_s, str):
        raise ConstraintError("deadline_invalid")
    try:
        at = datetime.strptime(at_s.strip()[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=config.ASTANA_TZ)
    except ValueError:
        raise ConstraintError("deadline_invalid") from None
    buffer_min = _int(raw.get("buffer_min"), "bad_buffer", 0, 60, default=10)
    seconds = (at - now).total_seconds()
    if seconds <= 0:
        # Never silently move a past time to tomorrow: the user must pick the date explicitly.
        raise ConstraintError("deadline_past", at=at.strftime("%H:%M"))
    if seconds > 24 * 3600:
        raise ConstraintError("deadline_too_far")
    minutes_left = int(seconds // 60)
    cap = minutes_left - buffer_min
    if cap <= 0:
        raise ConstraintError("deadline_buffer", left=minutes_left, buffer=buffer_min)
    return {"at": at.strftime("%Y-%m-%dT%H:%M"), "at_time": at.strftime("%H:%M"),
            "next_day": at.date() != now.date(), "buffer_min": buffer_min,
            "minutes_left": minutes_left, "cap_min": cap}


def resolve(body: dict, now: datetime | None = None) -> Constraints:
    now = now or datetime.now(config.ASTANA_TZ)
    text = str(body.get("text") or "")
    setting = _int(body.get("budget"), "bad_budget", MIN_MINUTES, MAX_MINUTES, default=60)
    text_min = parse_minutes(text)
    if text_min is not None:
        text_min = max(MIN_MINUTES, min(MAX_MINUTES, text_min))
    interests = _interests(body.get("interests"))
    pace = _pace(body.get("pace"))
    back = bool(body.get("back", True))

    limits: dict = {"setting": setting, "text": text_min, "group": None, "deadline": None}
    participants: list[Participant] = []
    group = body.get("group")
    if group:
        if not isinstance(group, dict) or not isinstance(group.get("participants"), list):
            raise ConstraintError("bad_group")
        plist = group["participants"]
        if not 2 <= len(plist) <= 5:
            raise ConstraintError("bad_group_size", min=2, max=5)
        for p in plist:
            if not isinstance(p, dict):
                raise ConstraintError("bad_group")
            participants.append(Participant(interests=_interests(p.get("interests")),
                                            minutes=_int(p.get("minutes"), "bad_budget", MIN_MINUTES, MAX_MINUTES),
                                            pace=_pace(p.get("pace"))))
        limits["group"] = min(p.minutes for p in participants)
        pace = min((p.pace for p in participants), key=PACE_ORDER.index)  # the slowest pace wins
        merged = []
        for p in participants:
            for i in p.interests:
                if i not in merged:
                    merged.append(i)
        interests = merged

    if participants:
        base, source = limits["group"], "group"
        if text_min is not None and text_min < base:
            base, source = text_min, "text"
    elif text_min is not None:
        base, source = text_min, "text"
    else:
        base, source = setting, "setting"

    deadline = None
    dl = body.get("deadline")
    if dl and isinstance(dl, dict) and dl.get("enabled", True):
        deadline = parse_deadline(dl, now)
        limits["deadline"] = deadline["cap_min"]
        back = True  # "back by" means returning to the start point
        if deadline["cap_min"] < base:
            base, source = deadline["cap_min"], "deadline"
    elif dl not in (None, False, {}) and not isinstance(dl, dict):
        raise ConstraintError("deadline_invalid")

    outdoor_max, strict = None, False
    od = body.get("outdoor")
    if od:
        if not isinstance(od, dict):
            raise ConstraintError("bad_outdoor")
        if od.get("max_min") not in (None, ""):
            outdoor_max = _int(od.get("max_min"), "bad_outdoor", 0, 240)
        strict = bool(od.get("strict", False))

    ex = body.get("exclude") or {}
    if not isinstance(ex, dict):
        raise ConstraintError("bad_exclusions")
    exclude = {"visited": _ids(ex.get("visited")), "unavailable": _ids(ex.get("unavailable")),
               "other": _ids(ex.get("other"))}

    flt = body.get("filters") or {}
    if not isinstance(flt, dict) or any(not isinstance(flt.get(k, False), bool) for k in ("known_hours", "wheelchair")):
        raise ConstraintError("bad_filters")
    if not isinstance(body.get("broaden", False), bool):
        raise ConstraintError("bad_filters")
    return Constraints(now=now, budget_min=int(base), budget_source=source, limits=limits, pace=pace,
                       speed=PACES[pace], return_to_start=back, interests=interests, deadline=deadline,
                       outdoor_max=outdoor_max, outdoor_strict=strict, participants=participants, exclude=exclude,
                       filters={"known_hours": bool(flt.get("known_hours")), "wheelchair": bool(flt.get("wheelchair"))},
                       broaden=bool(body.get("broaden", False)))


def eta(now: datetime, minutes: int) -> str:
    return (now + timedelta(minutes=minutes)).strftime("%H:%M")
