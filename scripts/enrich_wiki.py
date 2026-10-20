"""Add photos (Wikimedia Commons) and short descriptions (Wikipedia/Wikidata) to data/pois.json.

Usage (PowerShell, from the project folder, after collect_osm.py):
    .venv\\Scripts\\python scripts\\enrich_wiki.py
    .venv\\Scripts\\python scripts\\enrich_wiki.py --refresh   # ignore the 30-day local cache
Only places that OpenStreetMap links to Wikidata/Commons get media. If it fails, the file is unchanged.
Optional: $env:WIKI_CONTACT = "https://github.com/<you>"  (sent in the User-Agent, as Wikimedia asks)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walks import config  # noqa: E402
from walks.enrich import EnrichError, enrich_file  # noqa: E402


def main() -> int:
    refresh = "--refresh" in sys.argv[1:]
    try:
        stats = enrich_file(config.DATA_PATH, refresh=refresh)
    except EnrichError as exc:
        print(f"Enrichment failed: {exc}\nYour dataset was NOT changed. Check your internet and try again later.")
        return 1
    print(f"Done: {stats['linked']} places linked to Wikidata, {stats['photos']} with a photo, "
          f"{stats['descriptions']} with a description.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
