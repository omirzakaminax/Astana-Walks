"""Conservative duplicate detection for places mapped more than once in OpenStreetMap.

Merged only when it is very likely the SAME place, and every merge records why:
* ``node_and_area``  – the same name as a point AND as an outline/relation (typical for malls,
                        parks, museums), same kind of place, close together;
* ``cross_script``    – one record named in Cyrillic, the other in Latin script, same kind, close
                        ("Мега Силк Вей" / "Mega Silk Way");
* ``same_point``      – identical name and kind less than 30 m apart (a point mapped twice).

Never merged: nearby branches of the same brand (two separate points with the same name),
places whose house numbers differ, a park and an attraction inside it, a monument and an
artwork of a different category, names that differ in their numbers. The record with more tags
is kept; the other record's ID is kept in ``merged_ids`` (old saved plans still resolve) and its
names are kept as search aliases with their source — never re-labelled as another language.
"""
from __future__ import annotations

from .geo import haversine_m
from .translit import has_cyrillic, same_name

# Categories that are effectively the same kind of place for duplicate purposes.
_FAMILY = {"restaurant": "food", "cafe": "food", "fast_food": "food", "ice_cream": "food"}
_BIG = {"mall", "park", "theme_park", "zoo", "campus", "sports", "museum", "theatre", "worship", "stadium"}


def _names(p: dict) -> list[str]:
    out = [p.get("name") or ""]
    out += [v for v in (p.get("names") or {}).values() if v]
    return [n for n in out if n]


def _kind(p: dict) -> str:
    return str(p.get("id", "")).split(":")[-1].split("/")[0]  # node | way | relation


def _addr(p: dict) -> tuple:
    t = p.get("osm_tags") or {}
    return (t.get("addr:street"), t.get("addr:housenumber"))


def match_reason(a: dict, b: dict) -> str | None:
    """Why a and b are the same place, or None."""
    if a["id"] == b["id"]:
        return "same_id"
    if a.get("name_is_generated") or b.get("name_is_generated"):
        return None
    if _FAMILY.get(a["category"], a["category"]) != _FAMILY.get(b["category"], b["category"]):
        return None
    aa, ab = _addr(a), _addr(b)
    if aa[1] and ab[1] and aa != ab:
        return None  # different addresses: different places (e.g. two branches)
    d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    big = a["category"] in _BIG or b["category"] in _BIG
    if d > (350 if big else 120):
        return None  # cheap distance check before the (slower) name comparison
    if not any(same_name(x, y) for x in _names(a) for y in _names(b)):
        return None
    if _kind(a) != _kind(b) and d <= (350 if big else 120):
        return "node_and_area"
    if has_cyrillic(a.get("name", "")) != has_cyrillic(b.get("name", "")) and d <= (250 if big else 80):
        return "cross_script"
    if (a.get("name") or "").strip().lower() == (b.get("name") or "").strip().lower() and d <= 30:
        return "same_point"
    return None


def is_duplicate(a: dict, b: dict) -> bool:
    return match_reason(a, b) is not None


def merge_duplicates(pois: list[dict]) -> tuple[list[dict], int]:
    """Return (unique places, number merged). Order: richer records first, then original order."""
    order = {id(p): i for i, p in enumerate(pois)}
    ranked = sorted(pois, key=lambda p: (-len(p.get("osm_tags") or {}), order[id(p)]))
    kept: list[dict] = []
    grid: dict[tuple[int, int], list[dict]] = {}   # ~550 x 350 m cells: compare only nearby records
    cell = lambda q: (int(q["lat"] / 0.005), int(q["lon"] / 0.005))
    merged = 0
    for p in ranked:
        dup, why = None, None
        cy, cx = cell(p)
        near = [k for dy in (-1, 0, 1) for dx in (-1, 0, 1) for k in grid.get((cy + dy, cx + dx), [])]
        for k in sorted(near, key=lambda k: order[id(k)] if id(k) in order else 0):
            why = match_reason(k, p)
            if why:
                dup = k
                break
        if dup is None:
            kept.append(p)
            grid.setdefault(cell(p), []).append(p)
            continue
        merged += 1
        if dup["id"] != p["id"]:
            dup.setdefault("merged_ids", []).append(p["id"])
            dup.setdefault("merges", []).append({
                "id": p["id"], "reason": why,
                "distance_m": round(haversine_m(dup["lat"], dup["lon"], p["lat"], p["lon"]))})
        # Explicit name:xx tags of the other OSM element are real localized names (with provenance).
        names, src = dup.setdefault("names", {}), dup.setdefault("name_src", {})
        for lang, v in (p.get("names") or {}).items():
            if lang not in names and (p.get("name_src") or {}).get(lang):
                names[lang] = v
                src[lang] = {"source": "osm", "element": p["id"]}
        aliases = dup.setdefault("aliases", [])
        for text in [p.get("name")] + [a.get("text") for a in p.get("aliases") or [] if isinstance(a, dict)]:
            if text and text != dup.get("name") and not any(a.get("text") == text for a in aliases):
                aliases.append({"text": text, "kind": "merged_record_name", "source": p["id"]})
        if not dup.get("opening_hours") and p.get("opening_hours"):
            dup["opening_hours"] = p["opening_hours"]
        if p.get("notable"):
            dup["notable"] = True
    kept.sort(key=lambda p: order[id(p)])
    return kept, merged
