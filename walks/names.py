"""Provenance-aware place names (one policy for the API, the page, exports and the model).

Every place keeps several kinds of names apart:

* ``name``          the original OpenStreetMap ``name`` tag (never changed);
* ``names``         explicit localized OSM tags ``name:kk`` / ``name:ru`` / ``name:en`` — rebuilt from
                    ``osm_tags`` on every load, so nothing can claim to be a ``name:en`` without a tag;
* ``name_src``      for each localized name: which OSM element it came from;
* ``aliases``       everything else that should find the place in search — ``official_name``,
                    ``alt_name``, ``short_name``, ``old_name``, names of merged duplicate records,
                    old (unverified) names from earlier dataset versions, the Latin transliteration;
* ``media.labels``  Wikidata labels, used for display only when the Wikidata item passed the
                    identity check (walks/enrich.py: not a person, coordinates near the place).

Display policy for a language L (first match wins):
  A. a reviewed override from data/name_overrides.json (keyed by POI ID, with source URL and date);
  B. the explicit OSM tag ``name:L`` (or the original name when OSM says it *is* the ``name:L``);
  C. the Wikidata label in L, if the item passed the identity check;
  D. the ORIGINAL name, unchanged, plus a localized place-type descriptor. For English we may
     add a clearly labelled *descriptive translation* of generic words ("көпірі" -> "Bridge"),
     and a Latin pronunciation aid. Neither is presented as an official name.

The alphabet is never used to decide which language a name is in.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .categories import LANGS, label
from .translit import has_cyrillic, to_latin

NAME_TAG_KEYS = ("official_name", "alt_name", "short_name", "old_name", "loc_name", "int_name", "reg_name")
GENERATED = {"en": "Playground (no name in OpenStreetMap)", "ru": "Детская площадка (без названия в OSM)",
             "kk": "Балалар алаңы (OSM-де атауы жоқ)"}

# Reviewed glossary of GENERIC Kazakh place-type words in their possessive form (the form used after
# a proper name: "Атырау көпірі" = "the Atyrau bridge"). Only physical place types; never institutions,
# so no institutional title is ever invented. Used for a labelled descriptive translation only.
KK_GENERIC_EN = {
    "көпірі": "Bridge", "саябағы": "Park", "шіркеуі": "Church", "мешіті": "Mosque", "алаңы": "Square",
    "ескерткіші": "Monument", "субұрқағы": "Fountain", "гүлзары": "Garden", "соборы": "Cathedral",
    "аллеясы": "Alley", "бульвары": "Boulevard",
}
_PROPER_WORD = re.compile(r"^[A-ZА-ЯЁӘІҢҒҮҰҚӨҺ][a-zа-яёәіңғүұқөһ]{2,}$")

_overrides_cache: dict = {"path": None, "mtime": None, "data": {}}


# ------------------------------------------------------------------ overrides
def load_overrides(path: Path | str | None) -> dict:
    """{poi_id: {lang: {"text", "kind", "source_url", "reviewed"}}}. Invalid entries are ignored."""
    if not path:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _overrides_cache["path"] == str(path) and _overrides_cache["mtime"] == mtime:
        return _overrides_cache["data"]
    out: dict = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    for e in (raw.get("overrides") if isinstance(raw, dict) else None) or []:
        if not isinstance(e, dict):
            continue
        pid, lang, text = e.get("id"), e.get("lang"), e.get("text")
        url, reviewed = e.get("source_url"), e.get("reviewed")
        kind = e.get("kind", "official_name")
        if not (isinstance(pid, str) and lang in LANGS and isinstance(text, str) and text.strip()):
            continue
        if not (isinstance(url, str) and re.match(r"^https://[^\s\"'<>]+$", url)):
            continue  # an override without a checkable source is not accepted
        if not (isinstance(reviewed, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", reviewed)):
            continue
        if kind not in ("official_name", "common_name", "translated_description"):
            continue
        out.setdefault(pid, {})[lang] = {"text": text.strip()[:120], "kind": kind, "source_url": url,
                                         "reviewed": reviewed, "note": str(e.get("note") or "")[:200]}
    _overrides_cache.update(path=str(path), mtime=mtime, data=out)
    return out


# ------------------------------------------------------------------ normalisation on load
def tag_names(tags: dict) -> dict[str, str]:
    """name:xx tags for our three languages (exact tags only)."""
    out = {}
    for lang in LANGS:
        v = (tags or {}).get(f"name:{lang}")
        if isinstance(v, str) and v.strip():
            out[lang] = v.strip()[:160]
    return out


def normalize_names(poi: dict) -> None:
    """Rebuild verified names from the record's own OSM tags; demote everything else to aliases.

    Older dataset versions stored names that were guessed from the alphabet (dedup) or copied
    from Wikidata without a provenance record. They are kept as search aliases with kind
    "legacy_unverified" and are never displayed as a localized name.
    """
    tags = poi.get("osm_tags") or {}
    verified = tag_names(tags)
    legacy = poi.get("names") if isinstance(poi.get("names"), dict) else {}
    aliases: list[dict] = []

    def add(text, kind, source=None):
        if isinstance(text, str) and text.strip() and text.strip() != poi.get("name"):
            t = text.strip()[:160]
            if not any(a["text"] == t for a in aliases):
                aliases.append({"text": t, "kind": kind, **({"source": source} if source else {})})

    for lang, v in legacy.items():
        if verified.get(lang) != v:
            add(v, "legacy_unverified")
    for key in NAME_TAG_KEYS:
        for k, v in tags.items():
            if k == key or k.startswith(key + ":"):
                for part in str(v).split(";"):
                    add(part, key)
    for lang, v in verified.items():
        add(v, f"name:{lang}")
    for a in poi.get("aliases") or []:          # aliases saved by a newer collector run
        if isinstance(a, dict):
            add(a.get("text"), a.get("kind", "alias"), a.get("source"))
    poi["names"] = verified
    poi["name_src"] = {lang: {"source": "osm", "element": poi.get("id")} for lang in verified}
    poi["aliases"] = aliases


def original_language(poi: dict) -> str | None:
    """Language of the original name ONLY when OSM says so (name == name:xx). Otherwise None."""
    tags = poi.get("osm_tags") or {}
    for lang in LANGS:
        if tags.get(f"name:{lang}") and tags.get(f"name:{lang}") == poi.get("name"):
            return lang
    return None


# ------------------------------------------------------------------ display
def descriptive_translation_en(name: str) -> str | None:
    """'Атырау көпірі' -> 'Atyrau Bridge' (labelled as a descriptive translation, not an official name).

    Only the exact pattern <one capitalised proper word> <generic word from the reviewed glossary>.
    Anything else (hyphenated words, initials, several words, grammatical cases) is left alone.
    """
    parts = (name or "").split()
    if len(parts) != 2 or not _PROPER_WORD.match(parts[0]):
        return None
    generic = KK_GENERIC_EN.get(parts[1].lower())
    if not generic:
        return None
    return f"{to_latin(parts[0])} {generic}"


def wikidata_label(poi: dict, lang: str) -> str | None:
    m = poi.get("media") or {}
    ident = m.get("identity") or {}
    if ident.get("status") != "ok":
        return None
    v = (m.get("labels") or {}).get(lang)
    return v.strip()[:160] if isinstance(v, str) and v.strip() else None


def current_overrides() -> dict:
    from . import config
    return load_overrides(config.NAME_OVERRIDES_PATH)


def resolve(poi: dict, lang: str, overrides: dict | None = None) -> dict:
    """One display name for one language, with provenance. See the module docstring for the order."""
    if overrides is None:
        overrides = current_overrides()
    original = poi.get("name") or ""
    if poi.get("name_is_generated"):
        return {"text": GENERATED.get(lang, GENERATED["en"]), "kind": "generated", "lang": lang, "original": None}
    ov = (overrides or {}).get(poi.get("id"), {}).get(lang)
    if ov:
        return {"text": ov["text"], "kind": "override", "label_kind": ov["kind"], "lang": lang,
                "source": ov["source_url"], "reviewed": ov["reviewed"], "original": original}
    tagged = (poi.get("names") or {}).get(lang)
    if tagged:
        src = (poi.get("name_src") or {}).get(lang, {}).get("element") or poi.get("id")
        return {"text": tagged, "kind": "osm", "lang": lang, "source": f"OSM name:{lang} ({src})",
                "original": original}
    if original_language(poi) == lang:
        return {"text": original, "kind": "osm", "lang": lang, "source": "OSM name", "original": original}
    wd = wikidata_label(poi, lang)
    if wd:
        qid = ((poi.get("media") or {}).get("identity") or {}).get("qid")
        return {"text": wd, "kind": "wikidata", "lang": lang, "source": f"Wikidata {qid}", "original": original}
    if lang == "en" and has_cyrillic(original):
        # A Latin-script name that OSM itself gives for this place (int_name, or the name of a merged
        # duplicate record). Shown as "Latin-script name from OSM" — not certified as English.
        for a in poi.get("aliases") or []:
            if a.get("kind") in ("int_name", "merged_record_name") and a.get("text") and not has_cyrillic(a["text"]):
                return {"text": a["text"], "kind": "osm_latin", "lang": None,
                        "source": f"OSM {a['kind']}" + (f" ({a['source']})" if a.get("source") else ""),
                        "original": original, "descriptor": label(poi.get("category", "other"), lang)}
    out = {"text": original, "kind": "original", "lang": original_language(poi), "original": original,
           "descriptor": label(poi.get("category", "other"), lang)}
    if lang == "en" and has_cyrillic(original):
        tr = descriptive_translation_en(original)
        if tr:
            out["translation"] = tr
        out["latin"] = to_latin(original)
    return out


def display_names(poi: dict, overrides: dict | None = None) -> dict:
    return {lang: resolve(poi, lang, overrides) for lang in LANGS}


def display_text(poi: dict, lang: str, overrides: dict | None = None) -> str:
    return resolve(poi, lang, overrides)["text"]


def search_strings(poi: dict, overrides: dict | None = None) -> list[str]:
    """Every string that should find this place: original, tags, aliases, labels, transliterations."""
    if overrides is None:
        overrides = current_overrides()
    out = [poi.get("name") or ""]
    out += list((poi.get("names") or {}).values())
    out += [a["text"] for a in poi.get("aliases") or [] if isinstance(a, dict) and a.get("text")]
    m = poi.get("media") or {}
    if (m.get("identity") or {}).get("status") == "ok":
        out += [v for v in (m.get("labels") or {}).values() if isinstance(v, str)]
    for lang_map in ((overrides or {}).get(poi.get("id")) or {}).values():
        out.append(lang_map["text"])
    tr = descriptive_translation_en(poi.get("name") or "")
    if tr:
        out.append(tr)
    seen, res = set(), []
    for s in out:
        for v in (s, to_latin(s)):
            v = (v or "").strip()
            if v and v.lower() not in seen:
                seen.add(v.lower())
                res.append(v)
    return res
