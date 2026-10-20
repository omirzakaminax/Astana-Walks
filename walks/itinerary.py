"""The canonical itinerary: ONE object holding the selected places, their order, the visit
durations shown on the cards, every walking leg (including the way back), arrival times,
outdoor exposure and opening-hours checks. Cards, map numbers, the timeline, exports,
replacements and Bingo all render from this object.

Rules
* Total = every walking leg + every displayed visit duration. Nothing is summed twice or
  replaced by a shorter value behind the user's back.
* Up to three stops: all orders are checked; the feasible order with the least total wins.
* If the plan does not fit, visits are shortened step by step (never below the category
  minimum, and the cards show the shortened value), then the lowest-priority stops are
  dropped. A plan that does not fit is never presented as fitting.
* Opening hours are checked at the estimated arrival time for the whole visit.
* Walking is straight-line distance x detour factor at the request's pace: an estimate,
  not navigation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations, permutations

from .categories import indoor_basis, visit_range
from .geo import approx_walk_minutes, haversine_m
from .hours import check_visit

MAX_STOPS = 3


@dataclass
class Stop:
    poi: dict
    visit_min: int
    priority: int = 0          # lower = more important (e.g. model's order)

    @property
    def id(self) -> str:
        return self.poi["id"]

    @property
    def range(self) -> tuple[int, int]:
        return visit_range(self.poi["category"])


@dataclass
class Context:
    start_lat: float
    start_lon: float
    start_name: str
    speed: float
    return_to_start: bool
    budget_min: int
    now: datetime
    outdoor_max: int | None = None
    outdoor_strict: bool = False
    # Where the walk ends when return_to_start is set. None = the start point. During an active walk
    # the start is the CURRENT position and this stays the ORIGINAL start (never the latest cafe).
    return_lat: float | None = None
    return_lon: float | None = None
    return_name: str | None = None

    @property
    def has_separate_return(self) -> bool:
        return self.return_lat is not None and self.return_lon is not None


@dataclass
class Plan:
    stops: list[dict]
    legs: list[dict]
    total_min: int
    walk_min: int
    visit_min: int
    outdoor_min: int
    outdoor_estimated: bool       # True if any indoor/outdoor value is only a category estimate
    budget_min: int
    return_to_start: bool
    end_eta: str
    adjustments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"stops": self.stops, "legs": self.legs, "total_min": self.total_min, "walk_min": self.walk_min,
                "visit_min": self.visit_min, "outdoor_min": self.outdoor_min,
                "outdoor_estimated": self.outdoor_estimated, "budget_min": self.budget_min,
                "spare_min": self.budget_min - self.total_min, "fits": self.total_min <= self.budget_min,
                "return_to_start": self.return_to_start, "end_eta": self.end_eta,
                "adjustments": self.adjustments}

    @property
    def ids(self) -> list[str]:
        return [s["id"] for s in self.stops]


def clamp_visit(poi: dict, minutes) -> int:
    lo, hi = visit_range(poi["category"])
    try:
        m = int(round(float(minutes)))
    except (TypeError, ValueError):
        m = (lo + hi) // 2
    return max(lo, min(hi, m))


def evaluate(order: list[Stop], ctx: Context) -> tuple[Plan | None, str | None]:
    """Compute one ordered plan. Returns (plan, None) if it fits, else (None, reason)."""
    t = 0
    legs, stops = [], []
    walk_total = visit_total = outdoor = 0
    estimated = False
    cur = ("start", ctx.start_lat, ctx.start_lon, ctx.start_name)
    for n, st in enumerate(order, start=1):
        d = haversine_m(cur[1], cur[2], st.poi["lat"], st.poi["lon"])
        w = approx_walk_minutes(d, ctx.speed)
        legs.append({"from": cur[0], "from_name": cur[3], "to": st.id, "to_name": st.poi["name"],
                     "distance_m": round(d), "walk_min": w})
        t += w
        walk_total += w
        outdoor += w
        arrival = ctx.now + timedelta(minutes=t)
        hours_check = check_visit(st.poi.get("opening_hours"), arrival, st.visit_min)
        if hours_check == "closed":
            return None, "hours"
        indoor, basis = indoor_basis(st.poi)
        counts_outdoor = (not indoor) or (ctx.outdoor_strict and basis != "osm_tag")
        if basis != "osm_tag":
            estimated = True
        if counts_outdoor:
            outdoor += st.visit_min
        stops.append({"n": n, "id": st.id, "category": st.poi["category"], "visit_minutes": st.visit_min, "visit_range": list(st.range),
                      "arrive_offset_min": t, "leave_offset_min": t + st.visit_min,
                      "arrive_at": arrival.strftime("%H:%M"),
                      "leave_at": (arrival + timedelta(minutes=st.visit_min)).strftime("%H:%M"),
                      "walk_from_prev_min": w, "distance_from_prev_m": round(d),
                      "hours_at_arrival": hours_check, "indoor": indoor, "indoor_basis": basis,
                      "counts_outdoor": counts_outdoor})
        t += st.visit_min
        visit_total += st.visit_min
        cur = (st.id, st.poi["lat"], st.poi["lon"], st.poi["name"])
    if ctx.return_to_start and order:
        if ctx.has_separate_return:
            rl, rn, rto, rname = ctx.return_lat, ctx.return_lon, "return", ctx.return_name or ""
        else:
            rl, rn, rto, rname = ctx.start_lat, ctx.start_lon, "start", ctx.start_name
        d = haversine_m(cur[1], cur[2], rl, rn)
        w = approx_walk_minutes(d, ctx.speed)
        legs.append({"from": cur[0], "from_name": cur[3], "to": rto, "to_name": rname,
                     "distance_m": round(d), "walk_min": w})
        t += w
        walk_total += w
        outdoor += w
    if t > ctx.budget_min:
        return None, "time"
    if ctx.outdoor_max is not None and outdoor > ctx.outdoor_max:
        return None, "outdoor"
    plan = Plan(stops=stops, legs=legs, total_min=t, walk_min=walk_total, visit_min=visit_total,
                outdoor_min=outdoor, outdoor_estimated=estimated, budget_min=ctx.budget_min,
                return_to_start=ctx.return_to_start, end_eta=(ctx.now + timedelta(minutes=t)).strftime("%H:%M"))
    return plan, None


def best_order(stops: list[Stop], ctx: Context) -> tuple[Plan | None, str | None]:
    """Try every order (<= 3 stops); keep the feasible one with the smallest total."""
    best, reasons = None, []
    for perm in permutations(stops):
        plan, why = evaluate(list(perm), ctx)
        if plan and (best is None or plan.total_min < best.total_min):
            best = plan
        elif why:
            reasons.append(why)
    if best:
        return best, None
    # Report the most informative reason: hours > outdoor > time.
    for r in ("hours", "outdoor", "time"):
        if r in reasons:
            return None, r
    return None, "time"


def fit_plan(stops: list[Stop], ctx: Context) -> tuple[Plan | None, list[dict], str | None]:
    """Find a feasible plan from `stops` (in priority order).

    1. all stops with the displayed visit durations;
    2. the same stops with visits shortened in 5-minute steps (never below the category minimum);
    3. subsets, dropping the lowest-priority stops first.
    Returns (plan, adjustments, failure_reason).
    """
    stops = sorted(stops[:MAX_STOPS], key=lambda s: s.priority)
    last_reason = None
    for size in range(len(stops), 0, -1):
        subsets = list(combinations(stops, size))
        subsets.sort(key=lambda c: sum(s.priority for s in c))  # keep the most important first
        for subset in subsets:
            subset = list(subset)
            dropped = [s for s in stops if s not in subset]
            cut = 0
            while True:
                trial = [Stop(s.poi, max(s.range[0], s.visit_min - cut), s.priority) for s in subset]
                plan, why = best_order(trial, ctx)
                if plan:
                    adj = [{"code": "dropped", "id": s.id, "reason": last_reason or why or "time"} for s in dropped]
                    for s, tr in zip(subset, trial):
                        if tr.visit_min != s.visit_min:
                            adj.append({"code": "shortened", "id": s.id, "from": s.visit_min, "to": tr.visit_min,
                                        "reason": last_reason or "time"})
                    plan.adjustments = adj
                    return plan, adj, None
                last_reason = why
                if why == "hours" or all(tr.visit_min == s.range[0] for tr, s in zip(trial, subset)):
                    break
                cut += 5
    return None, [], last_reason or "time"


def outdoor_single(poi: dict, walk_min: int, ctx: Context) -> int:
    # (pre-filter estimate; the full itinerary, including a separate return point, is checked later)
    """Outdoor minutes of a one-stop round trip (used to pre-filter candidates)."""
    lo, _ = visit_range(poi["category"])
    indoor, basis = indoor_basis(poi)
    visit_out = lo if ((not indoor) or (ctx.outdoor_strict and basis != "osm_tag")) else 0
    return walk_min * (2 if ctx.return_to_start else 1) + visit_out
