"""Collect real POIs around a point in Astana from OpenStreetMap and save data/pois.json.

Usage (PowerShell, from the project folder):
    .venv\\Scripts\\python scripts\\collect_osm.py
    .venv\\Scripts\\python scripts\\collect_osm.py --lat 51.0890 --lon 71.4160 --radius 2500
    .venv\\Scripts\\python scripts\\collect_osm.py --area centre --merge   # add a second area
    .venv\\Scripts\\python scripts\\collect_osm.py --landmarks --merge     # notable places citywide
    .venv\\Scripts\\python scripts\\collect_osm.py --all                   # all of the above, merged

If collection fails, the existing data/pois.json is left untouched.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walks import config  # noqa: E402
from walks.geo import InvalidCoordinates  # noqa: E402
from walks.osm_collect import DEFAULT_CENTER, DEFAULT_RADIUS_M, CollectionError, collect  # noqa: E402

# Preset centres (approximate coordinates of well-known areas).
AREAS = {
    "expo": DEFAULT_CENTER,            # EXPO / Astana IT University
    "centre": (51.1290, 71.4200),      # between Baiterek and Khan Shatyr (Nurzhol boulevard)
    "right_bank": (51.1650, 71.4300),  # older right-bank centre (Respublika Ave, Central Park)
}


def run_all(args) -> int:
    steps = [("expo", False), ("centre", False), ("right_bank", False), (None, True)]
    ok = 0
    for i, (area, landmarks) in enumerate(steps):
        center = AREAS[area] if area else AREAS["expo"]
        label = "landmarks (citywide)" if landmarks else area
        print(f"\n=== {i + 1}/{len(steps)}: {label}")
        try:
            # Always merge: an existing real dataset is extended, never replaced.
            ds = collect(center, args.radius, args.max, args.out, merge=True, landmarks=landmarks)
            ok += 1
        except CollectionError as exc:
            print(f"Step failed, skipping it: {exc}")
        if i < len(steps) - 1:
            time.sleep(5)  # be polite to the public Overpass servers
    if not ok:
        print("All steps failed. Your existing dataset (if any) was NOT changed.")
        return 1
    m = ds["meta"]
    print(f"\nDone: {m['count']} places ({m.get('notable_count', 0)} notable), {ok}/{len(steps)} steps succeeded.")
    print("\n=== photos and descriptions (Wikidata / Wikimedia Commons / Wikipedia)")
    try:
        from walks.enrich import EnrichError, enrich_file
        st = enrich_file(args.out)
        print(f"{st['photos']} places with a photo, {st['descriptions']} with a description.")
    except Exception as exc:  # enrichment is optional; the collected data is already saved
        print(f"Skipped: {exc}. You can retry later with scripts\\enrich_wiki.py")
    for cat, n in m["counts_by_category"].items():
        print(f"  {cat:12s} {n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(AREAS), help="preset area (overrides --lat/--lon)")
    ap.add_argument("--lat", type=float, default=DEFAULT_CENTER[0])
    ap.add_argument("--lon", type=float, default=DEFAULT_CENTER[1])
    ap.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M, help="metres (500-6000)")
    ap.add_argument("--max", type=int, default=150, help="maximum places to keep (nearest first)")
    ap.add_argument("--out", type=Path, default=config.DATA_PATH)
    ap.add_argument("--merge", action="store_true", help="add to the existing dataset instead of replacing it")
    ap.add_argument("--landmarks", action="store_true",
                    help="collect notable places across the whole city (Wikipedia/Wikidata-linked, museums, sights)")
    ap.add_argument("--all", action="store_true",
                    help="EXPO + centre + right bank areas and citywide landmarks, merged into the existing file")
    args = ap.parse_args()
    if args.all:
        return run_all(args)
    if args.area:
        args.lat, args.lon = AREAS[args.area]
    if not 500 <= args.radius <= 6000:
        print("Radius must be between 500 and 6000 metres (keeps the public server load small).")
        return 2
    try:
        ds = collect((args.lat, args.lon), args.radius, args.max, args.out, merge=args.merge,
                     landmarks=args.landmarks)
    except InvalidCoordinates as exc:
        print(f"Invalid coordinates: {exc}")
        return 2
    except CollectionError as exc:
        print(f"Collection failed: {exc}")
        print("Your existing dataset (if any) was NOT changed. Check your internet connection "
              "and try again in a few minutes.")
        return 1
    m = ds["meta"]
    print(f"\nDone: {m['count']} places in the dataset, latest collection {m['collected_at']}")
    for cat, n in m["counts_by_category"].items():
        print(f"  {cat:12s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
