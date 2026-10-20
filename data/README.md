# data/

`pois.json` is created by `scripts/collect_osm.py` from OpenStreetMap (© OpenStreetMap contributors,
ODbL 1.0). It is **not included in the ZIP** (the build environment could not reach the Overpass API);
your own collected file stays on your laptop. Commit it to the repository so the demo does not depend
on a live request.

Other files here:
* `name_overrides.json` — reviewed name corrections (empty by default; see `docs/NAMING.md`).
* `backups/` — copies of `pois.json` made before each save (last 3; not committed).
* `cache/` — Wikimedia answers (30 days) and optional embeddings (not committed; safe to delete).
* `reports/` — output of `scripts/data_report.py` (actual counts).

Each record (schema version 2): `id` (e.g. `osm:node/123`), `source_url`, `name` (original), `names`
(explicit `name:kk/ru/en` tags only), `aliases` (other names with their kind), `merges` (if any), `lat`, `lon`, `category`,
`osm_tags` (selected), `opening_hours` (raw OSM text or null), `contacts`, `description`,
`description_source` (`osm_description_tag` or `summary_of_osm_tags`), `collected_at`, and for notable
places `media` (photo with author/licence from Wikimedia Commons; descriptions from Wikipedia/Wikidata).
`meta` holds the area, query, counts and collection timestamp.

The other datasets in the project, `tests/fixtures/synthetic_pois.json` and `tests/e2e/e2e_pois.json`, are **synthetic test
data** and must never be presented as real places.
