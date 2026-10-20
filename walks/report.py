"""Data-quality and naming audits for a loaded dataset (actual counts only).

Used by scripts/data_report.py. Writes Markdown + JSON. Nothing in the dataset is changed.
"""
from __future__ import annotations

from collections import Counter

from .categories import LANGS
from .hours import UnsupportedFormat, parse_week
from .names import resolve
from .translit import has_cyrillic


def naming_audit(ds) -> dict:
    per_lang = {lang: Counter() for lang in LANGS}
    unresolved_en, translations, legacy, generated = [], 0, [], 0
    for p in ds.pois:
        if p.get("name_is_generated"):
            generated += 1
            continue
        for lang in LANGS:
            r = resolve(p, lang)
            per_lang[lang][r["kind"]] += 1
            if lang == "en" and r["kind"] == "original" and has_cyrillic(p["name"]):
                if r.get("translation"):
                    translations += 1
                unresolved_en.append({"id": p["id"], "name": p["name"], "category": p["category"],
                                      "descriptive_translation": r.get("translation"),
                                      "pronunciation_aid": r.get("latin")})
        leg = [a["text"] for a in p.get("aliases") or [] if a.get("kind") == "legacy_unverified"]
        if leg:
            legacy.append({"id": p["id"], "name": p["name"], "legacy_names": leg})
    return {
        "places": len(ds.pois), "generated_names": generated,
        "display_name_source_by_language": {k: dict(v) for k, v in per_lang.items()},
        "english_original_name_fallback": len(unresolved_en),
        "english_with_descriptive_translation": translations,
        "records_with_legacy_unverified_names": len(legacy),
        "unresolved_english_examples": unresolved_en[:60],
        "legacy_examples": legacy[:40],
    }


def data_quality(ds) -> dict:
    cats = Counter(p["category"] for p in ds.pois)
    hours_raw = sum(1 for p in ds.pois if p.get("opening_hours"))
    hours_parsed = 0
    for p in ds.pois:
        if p.get("opening_hours"):
            try:
                parse_week(p["opening_hours"])
                hours_parsed += 1
            except (UnsupportedFormat, ValueError):
                pass
    wheel = Counter((p.get("osm_tags") or {}).get("wheelchair") or "not tagged" for p in ds.pois)
    media = Counter()
    ident = Counter()
    for p in ds.pois:
        m = p.get("media") or {}
        media["photo"] += "photo" in m
        media["description"] += "summary" in m
        if m.get("identity"):
            ident[m["identity"].get("status")] += 1
    merges = Counter()
    merge_examples = []
    for p in ds.pois:
        for m in p.get("merges") or []:
            merges[m["reason"]] += 1
            if len(merge_examples) < 25:
                merge_examples.append({"kept": p["id"], "name": p["name"], **m})
    areas = ds.meta.get("areas") or []
    return {
        "synthetic": ds.is_synthetic, "schema_version": ds.schema_version,
        "collected_at_latest": ds.meta.get("collected_at"),
        "areas": [{k: a.get(k) for k in ("kind", "center", "radius_m", "collected_at", "raw_elements", "kept", "added")}
                  for a in areas],
        "places": len(ds.pois), "skipped_on_load": ds.skip_reasons, "merged_on_load": ds.merged,
        "merges_by_reason": dict(merges), "merge_examples": merge_examples,
        "categories": dict(cats.most_common()),
        "linked_to_wikipedia_or_wikidata": sum(1 for p in ds.pois if p.get("notable")),
        "opening_hours": {"with_raw_text": hours_raw, "parseable_by_our_parser": hours_parsed,
                          "missing": len(ds.pois) - hours_raw},
        "wheelchair_tag": dict(wheel.most_common()),
        "media": {"with_photo": media["photo"], "with_description": media["description"],
                  "wikidata_identity": dict(ident)},
        "freshness_note": ("collected_at is when the data was DOWNLOADED from OpenStreetMap. It does not "
                           "mean opening hours or other details were verified on that date."),
    }


def to_markdown(dq: dict, na: dict, path_label: str) -> str:
    L = [f"# Data-quality and naming report", "", f"Dataset: `{path_label}`" +
         (" — **SYNTHETIC TEST DATA**" if dq["synthetic"] else ""), "",
         f"* Schema version: {dq['schema_version']}; latest collection: {dq['collected_at_latest']}",
         f"* Places after validation and merging: **{dq['places']}**; skipped on load: {dq['skipped_on_load'] or 'none'}; "
         f"merged on load: {dq['merged_on_load']} {dq['merges_by_reason'] or ''}",
         f"* Linked to Wikipedia/Wikidata (a link, not a popularity rating): {dq['linked_to_wikipedia_or_wikidata']}",
         f"* Opening hours: {dq['opening_hours']['with_raw_text']} with OSM text, "
         f"{dq['opening_hours']['parseable_by_our_parser']} parseable, {dq['opening_hours']['missing']} missing (shown as unknown)",
         f"* Wheelchair tag (source-reported): {dq['wheelchair_tag']}",
         f"* Media: {dq['media']['with_photo']} with a photo, {dq['media']['with_description']} with a description; "
         f"Wikidata identity checks: {dq['media']['wikidata_identity'] or 'not run yet'}",
         f"* {dq['freshness_note']}", "", "## Coverage (collected areas)", ""]
    for a in dq["areas"]:
        L.append(f"* {a.get('kind')}: centre {a.get('center')}, radius {a.get('radius_m') or 'citywide'} m, "
                 f"collected {a.get('collected_at')}, raw {a.get('raw_elements')}, kept {a.get('kept')}")
    if not dq["areas"]:
        L.append("* (no area metadata)")
    L += ["", "## Categories", ""] + [f"* {k}: {v}" for k, v in dq["categories"].items()]
    L += ["", "## Names", "", "Display-name source per interface language (see docs/NAMING.md):", ""]
    for lang, c in na["display_name_source_by_language"].items():
        L.append(f"* {lang}: {c}")
    L += ["", f"* English shows the ORIGINAL name (with an English type label): {na['english_original_name_fallback']} places; "
          f"of these {na['english_with_descriptive_translation']} also get a labelled descriptive translation.",
          f"* Records with old unverified names (kept only as search aliases): {na['records_with_legacy_unverified_names']}",
          f"* Unnamed places with a generated label: {na['generated_names']}", "",
          "### Places without a sourced English name (first 60)", "",
          "| ID | Original name | Type | Descriptive translation | Pronunciation aid |", "|---|---|---|---|---|"]
    for e in na["unresolved_english_examples"]:
        L.append(f"| {e['id']} | {e['name']} | {e['category']} | {e['descriptive_translation'] or ''} | {e['pronunciation_aid'] or ''} |")
    if na["legacy_examples"]:
        L += ["", "### Legacy names demoted to unverified aliases (first 40)", ""]
        for e in na["legacy_examples"]:
            L.append(f"* {e['id']} {e['name']}: {', '.join(e['legacy_names'])}")
    L += ["", "To fix a name: add a reviewed entry to data/name_overrides.json (ID, text, source URL, review date)."]
    return "\n".join(L) + "\n"
