"""Two or three alternative plan styles, built deterministically from the SAME eligible places.

  less_walking   – the feasible combination with the fewest walking minutes;
  more_variety   – the most different kinds of places, then the shortest total;
  less_outdoor   – the fewest estimated minutes outdoors.

Every alternative is a full itinerary checked by walks/itinerary.py against the same hard
constraints (time budget or deadline, opening hours at arrival, outdoor cap, return point).
Alternatives identical to the active plan or to each other are not shown, and nothing is shown
when only one plan fits. No model calls: the user picks a style, then the app explains it.
No "cheapest"/"safest" labels: we have no data for them.
"""
from __future__ import annotations

from itertools import combinations

from .categories import visit_range
from .retrieval import chain_key
from .itinerary import Context, Plan, Stop, best_order, clamp_visit

POOL_SIZE = 12


def _default_visit(poi: dict) -> int:
    lo, hi = visit_range(poi["category"])
    return clamp_visit(poi, lo + (hi - lo) // 3)


def _unknown_hours(plan: Plan) -> int:
    return sum(1 for s in plan.stops if s.get("hours_at_arrival") not in ("ok",))


def style_candidates(pool: list, per_cat: int = 3, limit: int = 12) -> list:
    """A DIVERSE slice of the ranked pool. The plain top 8 can be eight cafes, and then no
    "coffee + walk" alternative can exist (this was why en13 got no styles)."""
    out, n = [], {}
    for c in pool:
        cat = c.poi["category"]
        if n.get(cat, 0) < per_cat:
            out.append(c)
            n[cat] = n.get(cat, 0) + 1
        if len(out) >= limit:
            break
    return out


def build_styles(pool: list, ctx: Context, active_ids: list[str], size: int,
                 must_cover: list[list[str]] | None = None, active: Plan | None = None) -> list[dict]:
    return build_styles_with_status(pool, ctx, active_ids, size, must_cover, active)[0]


def build_styles_with_status(pool: list, ctx: Context, active_ids: list[str], size: int,
                             must_cover: list[list[str]] | None = None, active: Plan | None = None) -> tuple[list[dict], str]:
    """(styles, status). status: "ok" | "no_other_feasible_plan" | "current_is_best".
    pool: ranked eligible candidates. size: number of stops (1-3).
    must_cover: optional list of category lists, each must be hit (group / multi-intent coverage)."""
    cands = style_candidates(pool)
    size = max(1, min(3, size))
    plans: list[Plan] = []
    # Same number of stops as the active plan, and (for "more variety") up to three stops if time allows.
    for k in range(1, min(3, len(cands)) + 1):
        for combo in combinations(cands, k):
            if len({chain_key(c.poi) for c in combo}) < len(combo):
                continue  # two branches of the same chain in one walk
            if must_cover and not all(any(c.poi["category"] in cats for c in combo) for cats in must_cover if cats):
                continue
            plan, _ = best_order([Stop(c.poi, _default_visit(c.poi), i) for i, c in enumerate(combo)], ctx)
            if plan and frozenset(plan.ids) != frozenset(active_ids):
                plans.append(plan)
    if not plans:
        return [], "no_other_feasible_plan"

    by_id = {c.poi["id"]: c.poi for c in cands}
    if active is not None:
        for s_ in active.stops:
            by_id.setdefault(s_["id"], {"category": s_["category"]})

    def variety(p: Plan) -> int:
        return len({by_id[s["id"]]["category"] for s in p.stops})

    same_size = [p for p in plans if len(p.ids) == size] or plans
    picks = {
        "less_walking": min(same_size, key=lambda p: (p.walk_min, p.total_min)),
        "more_variety": min(plans, key=lambda p: (-variety(p), -len(p.ids), p.total_min, p.walk_min)),
        "less_outdoor": min(same_size, key=lambda p: (p.outdoor_min, p.total_min)),
    }
    def better(key: str, p: Plan) -> bool:
        """An alternative is shown only if it is really better on its own criterion."""
        if active is None:
            return True
        if key == "less_walking":
            return p.walk_min < active.walk_min
        if key == "less_outdoor":
            return p.outdoor_min < active.outdoor_min
        return variety(p) > len({by_id.get(s_["id"], {}).get("category") for s_ in active.stops})

    out, seen = [], {frozenset(active_ids)}
    for key, p in picks.items():
        ids = frozenset(p.ids)
        if ids in seen or not better(key, p):
            continue
        seen.add(ids)
        out.append({"key": key, "stop_ids": p.ids, "visit_minutes": [s["visit_minutes"] for s in p.stops],
                    "walk_min": p.walk_min, "total_min": p.total_min, "outdoor_min": p.outdoor_min,
                    "outdoor_estimated": p.outdoor_estimated, "unknown_hours": _unknown_hours(p),
                    "categories": [by_id[s["id"]]["category"] for s in p.stops], "end_eta": p.end_eta})
    return out, ("ok" if out else "current_is_best")


def describe_plan(plan: Plan, pool_by_id: dict) -> dict:
    """The same comparable numbers for the active plan."""
    return {"key": "current", "stop_ids": plan.ids, "walk_min": plan.walk_min, "total_min": plan.total_min,
            "outdoor_min": plan.outdoor_min, "outdoor_estimated": plan.outdoor_estimated,
            "unknown_hours": _unknown_hours(plan),
            "categories": [pool_by_id[i]["category"] for i in plan.ids if i in pool_by_id], "end_eta": plan.end_eta}
