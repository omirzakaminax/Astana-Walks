# Place names: policy, provenance and audit

## The problem we fixed

Earlier versions showed names like "Inzhil-lyuteran shirkeui", "Atyrau kopiri", "A. S. Pushkinu" on
the English page. Those were letter-by-letter transliterations of Kazakh/Russian names, shown as if
they were English. Two code paths did this (Python `display_name()` and JavaScript `displayName()`),
and the duplicate-merging step stored a second name as `ru` when it contained Cyrillic and as `en`
otherwise, so **the alphabet was used as if it were the language**. Wikidata labels could also fill
missing names without any record of where they came from.

## What a place stores now

| Field | Meaning | Source |
|---|---|---|
| `name` | the original OSM `name` tag, never changed | OpenStreetMap |
| `names` | only explicit `name:kk`, `name:ru`, `name:en` tags, **rebuilt from `osm_tags` on every load** | OpenStreetMap |
| `name_src` | which OSM element each localized name came from (e.g. a merged duplicate record) | code |
| `aliases` | `official_name`, `alt_name`, `short_name`, `old_name`, `int_name`, names of merged records, and old unverified names (`legacy_unverified`) — for **search only** | OSM / earlier versions |
| `media.labels` + `media.identity` | Wikidata labels, plus the result of the identity check | Wikidata |
| `data/name_overrides.json` | reviewed corrections keyed by POI ID, each with a source URL and review date | a person |

## Display policy (one implementation: `walks/names.py`, sent by the API for all three languages)

For interface language L, the first match wins:

1. **Reviewed override** for this POI ID and language (needs `source_url` and `reviewed` date, or it is ignored).
2. **Explicit OSM `name:L`**, or the original name when OSM states that it *is* the `name:L`.
3. **Wikidata label in L**, only if the item passed the identity check: not a person/name/disambiguation
   item, and its coordinates are within 2 km of the OSM record. (Items without coordinates may provide
   a photo/description but never a name.)
4. *(English only)* a **Latin-script name that OSM itself gives** for this place (`int_name`, or the name
   of a merged duplicate record such as "Mega Silk Way") — shown with the note "not confirmed as English".
5. Otherwise: the **original name unchanged**, plus a localized **place-type descriptor**
   ("Attraction", "Mosque, church or temple"). On the English page we may add:
   * a **descriptive translation**, only for the exact pattern *one proper word + a generic Kazakh
     place word from a reviewed glossary* (көпірі → Bridge, саябағы → Park, шіркеуі → Church,
     мешіті → Mosque, алаңы → Square, ескерткіші → Monument …), e.g. "Атырау көпірі" → "≈ Atyrau Bridge
     (descriptive translation, not an official name)". Hyphenated words, initials, several words and
     grammatical cases ("А. С. Пушкину") are left alone; institutions are never translated;
   * a **pronunciation aid** ("Reads as: Atyrau kopiri"), clearly labelled, never used as the name.

The page renders `poi.display_names[lang]` from the API. Switching the language updates every surface
instantly (start picker, cards, map titles, timeline, route, exports, Bingo) without a new model call;
if the AI text was written in another language, the page says so and offers to regenerate it.

## Search keeps every spelling

`walks/search.py` indexes the original name, every tag, every alias, verified Wikidata labels,
overrides, descriptive translations, Latin transliterations, a script-independent sound "skeleton",
and initials ("Astana IT University" → AITU). So "baiterek", "Байтерек", "Бәйтерек", "Байтерека"
(case ending) and "AITU" all find the right place. Only the collected dataset is searched; "not
found" is reported as "not in our dataset", never as "does not exist".

## Duplicates are merged conservatively

`walks/dedup.py` merges only: the same name as a point and as an outline (`node_and_area`), one
Cyrillic and one Latin name of the same kind close together (`cross_script`), or an identical name
under 30 m (`same_point`). Never: nearby branches of one brand, different house numbers, a park and
an attraction inside it, different categories, names that differ in numbers. Every merge records
`{id, reason, distance_m}`; the old ID keeps resolving for saved plans.

## Migration of an existing dataset

Nothing to do by hand: on load, `names` is rebuilt from the record's own tags and any other old name
becomes a `legacy_unverified` alias (still searchable, never displayed as a localized name). The
file on disk is not modified on load. Re-running `scripts\collect_osm.py --all` (which backs up the
old file to `data\backups\`) and `scripts\enrich_wiki.py` restores full provenance and stores the
Wikidata identity checks.

## Naming audit

`scripts\data_report.py` writes `data\reports\data_quality.md` with **actual counts**: display-name
source per language, places shown with their original name in English (with type and optional
descriptive translation), records whose old names were demoted, and the first 60 unresolved records.
The audit for your real dataset must be generated on your laptop (the build environment had no real
data and no access to OpenStreetMap).

## Reviewed overrides

`data\name_overrides.json` ships **empty**: we could not verify exact OSM IDs and sources from the
build environment, and we do not hard-code replacements for automatically collected data. To add one:

```json
{"id": "osm:way/123456", "lang": "en", "text": "Atyrau Bridge", "kind": "common_name",
 "source_url": "https://…page that names THIS bridge…", "reviewed": "2026-10-21", "note": "checked on site/map"}
```

`kind` is `official_name`, `common_name` or `translated_description` (shown as a translation, not an
official title). Check the ID on openstreetmap.org first; an entry without a valid source URL or
review date is ignored.
