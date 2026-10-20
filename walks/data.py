"""Load and validate the collected POI dataset (data/pois.json).

On load (in memory only — the file on disk is never modified here):
* every record is validated (ID, coordinates inside Astana, category, OpenStreetMap source URL,
  text lengths); invalid records are skipped and counted by reason;
* names are rebuilt from the record's own OSM tags (walks/names.py): names guessed by older
  versions are kept only as unverified search aliases;
* places mapped twice in OpenStreetMap are merged conservatively (walks/dedup.py), with the reason.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .categories import CATEGORIES, label
from .dedup import merge_duplicates
from .geo import InvalidCoordinates, validate_coords
from .names import normalize_names, resolve

REQUIRED_FIELDS = ("id", "name", "lat", "lon", "category", "source_url")
SCHEMA_VERSION = 2
ID_RE = re.compile(r"^osm:(node|way|relation)/\d{1,15}$")
SOURCE_RE = re.compile(r"^https://www\.openstreetmap\.org/(node|way|relation)/\d{1,15}$")
ANY_ID_RE = re.compile(r"^[A-Za-z0-9_:/.-]{1,80}$")          # synthetic test fixtures only
ANY_URL_RE = re.compile(r"^https?://[^\s\"'<>]{1,300}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class DatasetError(RuntimeError):
    pass


@dataclass
class Dataset:
    meta: dict
    pois: list[dict]
    by_id: dict[str, dict] = field(default_factory=dict)
    skipped: int = 0
    merged: int = 0
    skip_reasons: dict = field(default_factory=dict)
    schema_version: int = 1

    @property
    def is_synthetic(self) -> bool:
        return bool(self.meta.get("is_synthetic"))

    def get(self, poi_id: str) -> dict | None:
        return self.by_id.get(str(poi_id))


def _clean(v, limit: int) -> str:
    return _CTRL.sub(" ", str(v or "")).strip()[:limit]


def validate_poi(poi, synthetic: bool = False) -> str | None:
    """Return a skip reason, or None if the record is usable (it may be cleaned in place).

    Real datasets must use OpenStreetMap IDs and links; labelled synthetic fixtures may use their own."""
    if not isinstance(poi, dict):
        return "not_object"
    if any(poi.get(k) in (None, "") for k in REQUIRED_FIELDS):
        return "missing_field"
    if not (ANY_ID_RE if synthetic else ID_RE).match(str(poi["id"])):
        return "bad_id"
    if not (ANY_URL_RE if synthetic else SOURCE_RE).match(str(poi["source_url"])):
        return "bad_source_url"
    try:
        poi["lat"], poi["lon"] = validate_coords(poi["lat"], poi["lon"])
    except InvalidCoordinates:
        return "bad_coordinates"
    poi["name"] = _clean(poi["name"], 160)
    if not poi["name"]:
        return "missing_field"
    if poi["category"] not in CATEGORIES:
        poi["category"] = "other"
    for k, lim in (("description", 1000), ("opening_hours", 300)):
        if poi.get(k) is not None:
            poi[k] = _clean(poi[k], lim) or None
    if not isinstance(poi.get("osm_tags"), dict):
        poi["osm_tags"] = {}
    if not isinstance(poi.get("contacts"), dict):
        poi["contacts"] = {}
    ca = poi.get("collected_at")
    if ca is not None and not re.match(r"^\d{4}-\d{2}-\d{2}", str(ca)):
        poi["collected_at"] = None
    return None


def load_dataset(path: Path | str) -> Dataset:
    path = Path(path)
    if not path.exists():
        raise DatasetError(
            f"Dataset not found at {path}. Run the collector first: "
            "python scripts/collect_osm.py --all"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"Dataset file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("pois"), list):
        raise DatasetError("Dataset must be an object with a 'pois' list.")

    synthetic = bool((payload.get("meta") or {}).get("is_synthetic")) if isinstance(payload.get("meta"), dict) else False
    pois, seen, reasons = [], set(), Counter()
    for poi in payload["pois"]:
        why = validate_poi(poi, synthetic)
        if why is None and poi["id"] in seen:
            why = "duplicate_id"
        if why:
            reasons[why] += 1
            continue
        seen.add(poi["id"])
        poi.setdefault("opening_hours", None)
        poi.setdefault("description", "")
        poi.setdefault("description_source", "summary_of_osm_tags")
        tags = poi["osm_tags"]
        poi.setdefault("notable", bool(tags.get("wikidata") or tags.get("wikipedia")))
        normalize_names(poi)
        pois.append(poi)
    if not pois:
        raise DatasetError("Dataset contains no valid places.")
    pois, merged = merge_duplicates(pois)
    by_id: dict[str, dict] = {}
    for p in pois:
        by_id[p["id"]] = p
        for old in p.get("merged_ids", []):
            by_id.setdefault(old, p)  # an old ID from a saved plan still resolves
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    try:
        version = int(meta.get("schema_version", 1))
    except (TypeError, ValueError):
        version = 1
    return Dataset(meta=meta, pois=pois, by_id=by_id, skipped=sum(reasons.values()), merged=merged,
                   skip_reasons=dict(reasons), schema_version=version)


# ---------------------------------------------------------------- names and descriptions per language
def display_name(poi: dict, lang: str) -> tuple[str, bool]:
    """(name to show, is_original_fallback). Thin wrapper over walks.names.resolve (the only policy).

    The second value is True when no sourced name exists in `lang` and the original name is shown
    unchanged (with a place-type descriptor in the UI). Transliteration is NEVER returned as a name.
    """
    r = resolve(poi, lang)
    return r["text"], r["kind"] == "original"


_DESC = {
    "en": {"cuisine": "cuisine", "artwork_type": "artwork type", "sport": "sport", "operator": "operator",
           "outdoor_seating": "outdoor seating", "internet_access": "internet access", "wheelchair": "wheelchair access",
           "address": "address", "religion": "religion", "yes": "yes", "no": "no", "limited": "limited",
           "wlan": "Wi-Fi", "notable": "linked to Wikipedia/Wikidata"},
    "ru": {"cuisine": "кухня", "artwork_type": "тип объекта", "sport": "спорт", "operator": "оператор",
           "outdoor_seating": "места на улице", "internet_access": "интернет", "wheelchair": "доступ для колясок",
           "address": "адрес", "religion": "религия", "yes": "да", "no": "нет", "limited": "ограничен",
           "wlan": "Wi-Fi", "notable": "есть статья в Википедии/Викиданных"},
    "kk": {"cuisine": "асхана түрі", "artwork_type": "нысан түрі", "sport": "спорт", "operator": "операторы",
           "outdoor_seating": "сыртта отыратын орын", "internet_access": "интернет", "wheelchair": "арбамен кіру",
           "address": "мекенжайы", "religion": "діні", "yes": "иә", "no": "жоқ", "limited": "шектеулі",
           "wlan": "Wi-Fi", "notable": "Уикипедия/Уикидеректерде жазбасы бар"},
}


def describe(poi: dict, lang: str) -> tuple[str, str]:
    """(text, source). source = "osm_description_tag" (original text) or "summary_of_osm_tags"."""
    if poi.get("description_source") == "osm_description_tag" and poi.get("description"):
        return poi["description"], "osm_description_tag"
    d = _DESC.get(lang, _DESC["en"])
    tags = poi.get("osm_tags") or {}
    parts = [label(poi["category"], lang)]

    def val(v: str) -> str:
        return ", ".join(d.get(x.strip(), x.strip().replace("_", " ")) for x in str(v).split(";"))

    for key in ("cuisine", "artwork_type", "sport", "religion", "operator", "outdoor_seating",
                "internet_access", "wheelchair"):
        if tags.get(key):
            parts.append(f"{d[key]}: {val(tags[key]) if key != 'operator' else tags[key]}")
    addr = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
    if addr:
        parts.append(f"{d['address']}: {addr}")
    if poi.get("notable"):
        parts.append(d["notable"])
    return "; ".join(parts) + ".", "summary_of_osm_tags"


# Preferred starting landmarks, matched by name substring (if they exist in the data).
PREFERRED_START_NAMES = ["expo", "экспо", "нур алем", "нур-алем", "нұр әлем", "nur alem", "mega silk way", "мега силк",
                         "astana it university", "aitu", "байтерек", "бәйтерек", "baiterek", "bayterek",
                         "хан шатыр", "khan shatyr"]


def start_landmarks(ds: Dataset, limit: int = 40, grouped: bool = False) -> list:
    """Sourced places suggested as a (simulated) starting point. One entry per place.

    Groups (no popularity claim): "demo" – well-known starting points named in the docs, if present;
    "linked" – places OpenStreetMap links to Wikipedia/Wikidata; "sights" – other sights by type.
    With grouped=True returns (poi, group) pairs."""
    preferred, notable, others = [], [], []
    for poi in ds.pois:
        if poi.get("name_is_generated"):
            continue
        all_names = " ".join([poi["name"]] + list((poi.get("names") or {}).values())).lower()
        if any(p in all_names for p in PREFERRED_START_NAMES):
            preferred.append(poi)
        elif poi.get("notable"):
            notable.append(poi)
        elif poi["category"] in ("attraction", "mall", "museum", "park", "viewpoint", "theatre", "artwork",
                                 "worship", "stadium", "campus"):
            others.append(poi)
    notable.sort(key=lambda p: p["name"])
    others.sort(key=lambda p: p["name"])
    if grouped:
        out = [(p, "demo") for p in preferred] + [(p, "linked") for p in notable] + [(p, "sights") for p in others]
        return out[:limit]
    return (preferred + notable + others)[:limit]
