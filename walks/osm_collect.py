"""Automated POI collection from OpenStreetMap via the public Overpass API.

OpenStreetMap data is © OpenStreetMap contributors, licensed under ODbL 1.0.
We only read public map data, send a descriptive User-Agent, make one query per
run, back off on errors and never hammer the servers.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .categories import category_from_tags, label
from .geo import InvalidCoordinates, haversine_m, validate_coords
from .names import normalize_names

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "AstanaWalks-hackathon-prototype/1.0 (educational, non-commercial)"

# Default area: EXPO / Astana IT University district. Change with --lat/--lon/--radius.
DEFAULT_CENTER = (51.0890, 71.4160)
DEFAULT_RADIUS_M = 2500

KEEP_TAG_PREFIXES = ("amenity", "tourism", "leisure", "shop", "historic", "cuisine", "opening_hours",
                     "website", "phone", "contact:", "internet_access", "wheelchair", "outdoor_seating",
                     "artwork_type", "memorial", "sport", "description", "name", "operator", "addr:",
                     "diet:", "playground", "brand", "fee", "building", "indoor", "location", "covered",
                     "wikidata", "wikipedia", "religion", "denomination", "man_made", "image", "wikimedia_commons",
                     # all name variants with their language suffixes (provenance for walks/names.py)
                     "official_name", "alt_name", "short_name", "old_name", "loc_name", "int_name", "reg_name",
                     "charge")

# Whole-city bounding box (south, west, north, east) for the landmarks pass.
ASTANA_BBOX_SWNE = (51.02, 71.25, 51.25, 71.62)


class CollectionError(RuntimeError):
    pass


def build_query(lat: float, lon: float, radius_m: int) -> str:
    a = f"(around:{int(radius_m)},{lat:.6f},{lon:.6f})"
    return f"""[out:json][timeout:90];
(
  nwr{a}["amenity"~"^(cafe|restaurant|fast_food|ice_cream|cinema|theatre|concert_hall|library|arts_centre|fountain|university|place_of_worship)$"]["name"];
  nwr{a}["tourism"~"^(museum|gallery|zoo|aquarium|theme_park|viewpoint|artwork|attraction)$"];
  nwr{a}["leisure"~"^(park|garden|water_park|amusement_arcade|sports_centre|fitness_centre|stadium)$"]["name"];
  nwr{a}["leisure"="playground"];
  nwr{a}["historic"~"^(monument|memorial)$"]["name"];
  nwr{a}["shop"="mall"]["name"];
);
out center tags;"""


def build_landmarks_query(bbox=ASTANA_BBOX_SWNE) -> str:
    """Sights across the whole city: all named museums, attractions, viewpoints, monuments,
    parks, places of worship, theatres and malls, plus anything else tourist-related that OSM
    links to Wikipedia/Wikidata. "Notable" (Wikidata link) is a factual signal, not a rating."""
    b = "({:.4f},{:.4f},{:.4f},{:.4f})".format(*bbox)
    return f"""[out:json][timeout:180];
(
  nwr{b}["tourism"~"^(museum|attraction|viewpoint|gallery|zoo|aquarium|theme_park)$"]["name"];
  nwr{b}["wikidata"]["name"]["tourism"];
  nwr{b}["wikipedia"]["name"]["tourism"];
  nwr{b}["historic"~"^(monument|memorial)$"]["name"];
  nwr{b}["leisure"~"^(park|garden|stadium|water_park)$"]["name"];
  nwr{b}["amenity"~"^(theatre|concert_hall|arts_centre|place_of_worship|library)$"]["name"];
  nwr{b}["wikidata"]["name"]["amenity"="university"];
  nwr{b}["shop"="mall"]["name"];
);
out center tags;"""


def fetch_overpass(query: str, endpoints: list[str] | None = None, retries_per_endpoint: int = 2,
                   timeout_s: float = 120, session: requests.Session | None = None,
                   sleep=time.sleep, log=print) -> dict:
    """POST the query, trying mirrors with polite back-off. Raises CollectionError."""
    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    errors = []
    for url in endpoints or ENDPOINTS:
        for attempt in range(1, retries_per_endpoint + 1):
            try:
                log(f"  -> {url} (attempt {attempt})")
                r = s.post(url, data={"data": query}, timeout=timeout_s)
            except requests.exceptions.RequestException as exc:
                errors.append(f"{url}: {type(exc).__name__}")
                sleep(5 * attempt)
                continue
            if r.status_code == 200:
                try:
                    payload = r.json()
                except ValueError:
                    errors.append(f"{url}: response was not JSON")
                    break
                if "elements" not in payload:
                    errors.append(f"{url}: no 'elements' in response")
                    break
                return payload
            errors.append(f"{url}: HTTP {r.status_code}")
            if r.status_code in (429, 502, 503, 504):
                sleep(10 * attempt)  # server busy: wait, then retry
                continue
            break  # other errors: try next mirror
    raise CollectionError("All Overpass endpoints failed: " + "; ".join(errors))


def _kept_tags(tags: dict) -> dict:
    return {k: v for k, v in tags.items() if k.startswith(KEEP_TAG_PREFIXES)}


def summarize_tags(category: str, tags: dict) -> str:
    """A factual one-line summary built ONLY from source fields (no invented details)."""
    parts = [label(category, "en")]
    if tags.get("cuisine"):
        parts.append("cuisine: " + tags["cuisine"].replace(";", ", ").replace("_", " "))
    if tags.get("artwork_type"):
        parts.append("artwork type: " + tags["artwork_type"].replace("_", " "))
    if tags.get("sport"):
        parts.append("sport: " + tags["sport"].replace(";", ", ").replace("_", " "))
    if tags.get("operator"):
        parts.append("operator: " + tags["operator"])
    if tags.get("outdoor_seating"):
        parts.append("outdoor seating: " + tags["outdoor_seating"])
    if tags.get("internet_access"):
        parts.append("internet access: " + tags["internet_access"])
    if tags.get("wheelchair"):
        parts.append("wheelchair: " + tags["wheelchair"])
    addr = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    if addr:
        parts.append("address: " + addr)
    return "; ".join(parts) + ". (Summary of OpenStreetMap tags.)"


def normalize(elements: list[dict], center: tuple[float, float], radius_m: int | None,
              collected_at: str, max_unnamed_playgrounds: int = 8) -> list[dict]:
    """radius_m=None keeps everything inside Astana (citywide landmarks pass)."""
    pois, unnamed = [], []
    for el in elements:
        tags = el.get("tags") or {}
        etype, eid = el.get("type"), el.get("id")
        if etype not in ("node", "way", "relation") or eid is None:
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        try:
            lat, lon = validate_coords(lat, lon)
        except InvalidCoordinates:
            continue
        dist = haversine_m(center[0], center[1], lat, lon)
        if radius_m is not None and dist > radius_m * 1.05:
            continue
        category = category_from_tags(tags)
        name = re.sub(r"[\x00-\x1f\x7f]", " ", tags.get("name") or tags.get("name:kk") or tags.get("name:ru")
                      or tags.get("name:en") or "").strip()[:160]
        generated_name = False
        if not name:
            if category != "playground":
                continue  # unnamed places are not useful recommendations
            name, generated_name = "Детская площадка (без названия в OSM)", True
        has_desc = bool(tags.get("description"))
        poi = {
            "id": f"osm:{etype}/{eid}",
            "source": "OpenStreetMap (Overpass API)",
            "source_url": f"https://www.openstreetmap.org/{etype}/{eid}",
            "name": name,
            "name_is_generated": generated_name,
            "names": {},  # filled from the name:xx tags by walks.names.normalize_names (with provenance)
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "category": category,
            "osm_tags": _kept_tags(tags),
            "opening_hours": tags.get("opening_hours"),
            "contacts": {k: tags[t] for k, t in (("phone", "phone"), ("phone", "contact:phone"),
                                                 ("website", "website"), ("website", "contact:website"),
                                                 ("instagram", "contact:instagram")) if tags.get(t)},
            "description": tags["description"][:1000] if has_desc else summarize_tags(category, tags),
            "description_source": "osm_description_tag" if has_desc else "summary_of_osm_tags",
            "notable": bool(tags.get("wikidata") or tags.get("wikipedia")),
            "collected_at": collected_at,
            "_dist": dist,
        }
        normalize_names(poi)
        (unnamed if generated_name else pois).append(poi)
    unnamed.sort(key=lambda p: p["_dist"])
    return pois + unnamed[:max_unnamed_playgrounds]


def deduplicate(pois: list[dict]) -> list[dict]:
    """Remove exact ID duplicates and the same place mapped twice (node + building, or the
    same place with a Cyrillic and a Latin name). See walks/dedup.py."""
    from .dedup import merge_duplicates
    by_id = {}
    for p in pois:
        by_id.setdefault(p["id"], p)
    kept, _ = merge_duplicates(list(by_id.values()))
    kept.sort(key=lambda x: x.get("_dist", 0))
    return kept


def collect(center=DEFAULT_CENTER, radius_m=DEFAULT_RADIUS_M, max_pois=150, out_path: Path | None = None,
            fetch=fetch_overpass, log=print, merge: bool = False, landmarks: bool = False) -> dict:
    """Collect one area (around center) or, with landmarks=True, notable places citywide."""
    lat, lon = validate_coords(*center)
    if landmarks:
        query = build_landmarks_query()
        log("Querying Overpass for notable places across Astana ...")
    else:
        query = build_query(lat, lon, radius_m)
        log(f"Querying Overpass for POIs within {radius_m} m of ({lat}, {lon}) ...")
    payload = fetch(query)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    elements = payload.get("elements", [])
    log(f"Received {len(elements)} raw OSM elements.")
    cap_per_cat = 200 if landmarks else 40
    # Nearest first, capped per category so cafes cannot crowd out parks and museums.
    pois, per_cat = [], {}
    for p in deduplicate(normalize(elements, (lat, lon), None if landmarks else radius_m, collected_at,
                                   max_unnamed_playgrounds=0 if landmarks else 8)):
        if per_cat.get(p["category"], 0) >= cap_per_cat or len(pois) >= (400 if landmarks else max_pois):
            continue
        per_cat[p["category"]] = per_cat.get(p["category"], 0) + 1
        pois.append(p)
    for p in pois:
        p.pop("_dist", None)
    if not pois:
        raise CollectionError("Overpass answered, but no usable named places were found in this area.")
    area = {"kind": "landmarks" if landmarks else "area", "center": {"lat": lat, "lon": lon},
            "radius_m": None if landmarks else radius_m, "collected_at": collected_at,
            "raw_elements": len(elements), "kept": len(pois)}
    areas = [area]
    if merge and out_path and Path(out_path).exists():
        old = json.loads(Path(out_path).read_text(encoding="utf-8"))
        if old.get("meta", {}).get("is_synthetic"):
            raise CollectionError("Refusing to merge real data into a SYNTHETIC dataset file.")
        old_pois = old.get("pois", [])
        om = old.get("meta", {})
        old_areas = om.get("areas") or [{
            "kind": "area", "center": om.get("center"), "radius_m": om.get("radius_m"),
            "collected_at": om.get("collected_at"), "raw_elements": om.get("raw_elements"), "kept": len(old_pois)}]
        from .dedup import merge_duplicates
        for p in old_pois:
            if isinstance(p, dict) and isinstance(p.get("osm_tags"), dict):
                normalize_names(p)  # older files: names guessed from the alphabet become aliases
        combined, _ = merge_duplicates(list(old_pois) + pois)
        added = len(combined) - len(old_pois)
        log(f"Merged with existing file: {len(old_pois)} old + {added} new (skipped {len(pois) - added} duplicates).")
        area["added"] = added
        pois, areas = combined, old_areas + [area]
    counts: dict[str, int] = {}
    for p in pois:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    first = areas[0].get("center") or {"lat": lat, "lon": lon}
    dataset = {
        "meta": {
            "title": "Astana Walks POI dataset",
            "source": "OpenStreetMap via Overpass API",
            "license": "ODbL 1.0 — © OpenStreetMap contributors (https://www.openstreetmap.org/copyright)",
            "collected_at": collected_at,
            "center": first,
            "radius_m": areas[0].get("radius_m"),
            "raw_elements": sum(a.get("raw_elements") or 0 for a in areas),
            "areas": areas,
            "count": len(pois),
            "notable_count": sum(1 for p in pois if p.get("notable")),
            "counts_by_category": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "is_synthetic": False,
            "schema_version": 2,
            "query": query,
        },
        "pois": pois,
    }
    if out_path:
        save_atomic(dataset, Path(out_path))
        log(f"Saved {len(pois)} places to {out_path}")
    return dataset


def backup_file(path: Path, keep: int = 3) -> Path | None:
    """Copy an existing dataset to data/backups/<name>-<UTC time>.json before it is rewritten."""
    import shutil
    path = Path(path)
    if not path.exists():
        return None
    bdir = path.parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = bdir / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, target)
    old = sorted(bdir.glob(f"{path.stem}-*{path.suffix}"))
    for f in old[:-keep]:
        try:
            f.unlink()
        except OSError:
            pass
    return target


def save_atomic(dataset: dict, path: Path, backup: bool = True) -> None:
    """Back up the old file, write to a temp file, then rename: a failed run never corrupts the dataset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and not (dataset.get("meta") or {}).get("is_synthetic"):
        backup_file(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
