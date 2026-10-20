"""Retrieval: hard constraints in code + BM25 keyword ranking + proximity (+ weather).

Pipeline for one request:
1. Understand the request (intents, time budget, unsupported asks) - walks.text
2. Hard filters, computed in code, never by the LLM:
   * excluded places (start point, visited, reported unavailable, already in the plan)
   * category match with detected intents
   * distance + time budget at the request's pace (walk there [+ back] + minimum visit)
   * opening hours at the estimated ARRIVAL time, for a minimal visit
   * outdoor-exposure limit, if set (walking + outdoor visit time of a one-stop trip)
3. Rank survivors: 0.45 * BM25 text match + 0.35 * category fit + 0.20 * proximity
   (+ small bonuses: indoor places in harsh weather, notable landmarks for "must-see"
   requests, confirmed Wi-Fi / wheelchair tags, open late)
4. Keep a diverse top-K (max 2 per category; in group mode, balanced across people).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import config
from .categories import LANGS, is_indoor, label, visit_range
from .data import Dataset
from .geo import approx_walk_minutes, haversine_m, max_reachable_distance_m
from .hours import HoursStatus, check_visit, status_at
from .text import (INTENT_LABELS, INTENTS, categories_for, detect_intents, detect_language, detect_negations,
                   detect_unsupported, expansion_terms, mentions_flight, mentions_night, parse_minutes, tokenize, wants_notable)

DEFAULT_INTENTS = ["walk", "sights"]
TAG_KEYS_FOR_TEXT = ("amenity", "tourism", "leisure", "shop", "cuisine", "historic", "sport",
                     "artwork_type", "memorial", "diet:vegetarian", "religion")

# Codes for why places were filtered out (the UI translates them).
EXCL_CATEGORY = "category"
EXCL_TOO_FAR = "too_far"
EXCL_CLOSED = "closed"
EXCL_CLOSES_SOON = "closes_soon"
EXCL_OUTDOOR = "outdoor"
EXCL_USER = "excluded"
EXCL_NEGATED = "negated"              # the request said "no cafes" / "не музей"
EXCL_UNKNOWN_HOURS = "unknown_hours"  # filter "only places with known opening hours"
EXCL_NO_WHEELCHAIR = "no_wheelchair_info"  # filter: OSM wheelchair tag is not yes/limited (unknown != no)


class EmptyRequest(ValueError):
    code = "empty_request"


def _stem(token: str) -> str:
    return token[:5] if len(token) > 5 else token


def _stems(text: str) -> list[str]:
    return [_stem(t) for t in tokenize(text)]


def poi_document(poi: dict) -> str:
    from .translit import to_latin
    parts = [poi["name"], to_latin(poi["name"])]
    parts += [v for v in (poi.get("names") or {}).values() if v]
    if "expo" in " ".join(parts).lower():
        parts.append("экспо")
    cat = poi["category"]
    parts += [cat.replace("_", " ")] + [label(cat, lang) for lang in LANGS]
    tags = poi.get("osm_tags") or {}
    parts += [str(tags[k]).replace("_", " ").replace(";", " ") for k in TAG_KEYS_FOR_TEXT if k in tags]
    parts.append(poi.get("description") or "")
    return " ".join(parts)


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log((self.n - c + 0.5) / (c + 0.5) + 1) for t, c in df.items()}

    def score(self, query: list[str], i: int) -> float:
        tf, dl, s = self.tf[i], len(self.docs[i]), 0.0
        for t in set(query):
            f = tf.get(t, 0)
            if f:
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s


_BM25_CACHE: dict = {"ds": None, "bm25": None}


def _bm25_for(ds) -> BM25:
    """The BM25 index depends only on the loaded dataset: build it once per dataset object
    (server.get_dataset() returns a new object when data/pois.json changes)."""
    if _BM25_CACHE["ds"] is not ds or len(_BM25_CACHE["bm25"].docs) != len(ds.pois):
        _BM25_CACHE["bm25"] = BM25([_stems(poi_document(p)) for p in ds.pois])
        _BM25_CACHE["ds"] = ds
    return _BM25_CACHE["bm25"]


@dataclass
class Candidate:
    poi: dict
    distance_m: float
    walk_min: int
    hours: HoursStatus
    score: float
    parts: dict

    @property
    def id(self) -> str:
        return self.poi["id"]


@dataclass
class Request:
    text: str
    lat: float
    lon: float
    budget_min: int
    return_to_start: bool = True
    interests: list[str] = field(default_factory=list)
    now: datetime | None = None
    answer_lang: str | None = None   # "kk" | "ru" | "en"; default: language of the text
    weather: object | None = None    # walks.weather.Weather or None
    exclude_ids: tuple = ()          # start landmark, visited, unavailable, already selected
    speed: float | None = None       # m/min for this request only (pace)
    outdoor_max: int | None = None
    outdoor_strict: bool = False
    groups: list[list[str]] = field(default_factory=list)   # per-participant interests (group mode)
    budget_fixed: bool = False       # True: budget_min is already resolved (text cannot override it)
    max_distance_m: float | None = None   # e.g. "too far" replacement: closer than the old stop
    k: int | None = None
    exclude_categories: tuple = ()   # hard: never these categories (from negations or settings)
    known_hours_only: bool = False   # hard filter (source-based)
    wheelchair_only: bool = False    # hard filter: OSM wheelchair=yes|limited (source-reported)
    named_ids: tuple = ()            # places the user named as destinations ("visit Baiterek")
    broaden: bool = False            # one-click "any kind of place" (negations still apply)
    return_lat: float | None = None  # active walk: where to return (the ORIGINAL start), if different
    return_lon: float | None = None
    return_name: str | None = None


@dataclass
class RetrievalResult:
    lang: str                 # language of the answer
    query_lang: str           # language detected in the text
    intents: list[str]
    assumed_intents: bool
    target_categories: list[str]
    budget_min: int
    budget_source: str        # "text" | "slider" | "resolved"
    unsupported: list[str]
    night: bool
    candidates: list[Candidate]
    excluded: dict
    considered: int
    now: datetime
    weather: object | None = None
    pool: list[Candidate] = field(default_factory=list)   # all eligible, ranked (for surprise/replace)
    negated: list[str] = field(default_factory=list)      # categories excluded by the request text
    named: list[str] = field(default_factory=list)        # IDs of places named as destinations
    mode: str = "lexical"                                 # retrieval mode actually used
    mode_note: str | None = None                          # why hybrid was not used, if requested
    timings_ms: dict = field(default_factory=dict)
    named_excluded: dict = field(default_factory=dict)    # named places that failed a hard filter, and why
    named_pois: dict = field(default_factory=dict)
    flight: bool = False                                  # "before my flight": budget caveat shown


def retrieve(ds: Dataset, req: Request, k: int | None = None, require_text: bool = True) -> RetrievalResult:
    text = (req.text or "").strip()
    if require_text and not text and not req.interests and not req.groups:
        raise EmptyRequest("Please type what you would like to do or pick at least one interest.")
    k = k or req.k or config.CANDIDATES_FOR_LLM
    now = req.now or datetime.now(config.ASTANA_TZ)
    query_lang = detect_language(text) if text else (req.answer_lang or "en")
    lang = req.answer_lang if req.answer_lang in LANGS else query_lang
    speed = req.speed or config.WALK_SPEED_M_PER_MIN

    if req.budget_fixed:
        budget, budget_source = req.budget_min, "resolved"
    else:
        parsed_budget = parse_minutes(text)
        budget, budget_source = (parsed_budget, "text") if parsed_budget else (req.budget_min, "slider")
    budget = max(5, min(int(budget), 12 * 60))

    import time as _time
    t0 = _time.perf_counter()
    group_intents = [i for g in req.groups for i in g]
    intents = detect_intents(text, list(req.interests) + group_intents)
    negated = list(dict.fromkeys(list(detect_negations(text)[0]) + list(req.exclude_categories or ())))
    if req.broaden:
        intents = [i for i in INTENTS if i not in ("study", "sport")]
    assumed = not intents
    if assumed:
        # A tight outdoor limit with no stated interest means "somewhere warm", not "a walk".
        tight = req.outdoor_max is not None and req.outdoor_max <= 15
        intents = ["indoor"] if tight else list(DEFAULT_INTENTS)
    target = [c for c in categories_for(intents) if c not in negated]
    if not target and assumed is False:
        target = [c for c in categories_for(DEFAULT_INTENTS + ["coffee", "culture"]) if c not in negated]
    named = [i for i in (req.named_ids or ()) if ds.get(i)]
    named_real = {ds.get(i)["id"] for i in named}
    unsupported = detect_unsupported(text)
    night = mentions_night(text)
    notable_wanted = wants_notable(text)
    harsh = bool(getattr(req.weather, "harsh", False))
    excluded_ids = set(req.exclude_ids or ())

    query_tokens = [_stem(t) for t in tokenize(text)] + [_stem(t) for t in tokenize(" ".join(expansion_terms(intents)))]
    bm25 = _bm25_for(ds)

    from .itinerary import Context, outdoor_single
    octx = Context(req.lat, req.lon, "", speed, req.return_to_start, budget, now,
                   req.outdoor_max, req.outdoor_strict)

    excluded = Counter()
    pool: list[Candidate] = []
    named_excluded: dict[str, dict] = {}
    for i, poi in enumerate(ds.pois):
        code, info = _hard_filters(poi, req, target, negated, named_real, excluded_ids, budget, speed, now, octx)
        if code:
            excluded[code] += 1
            if poi["id"] in named_real:
                named_excluded[poi["id"]] = {"reason": code, **info}
            continue
        pool.append(Candidate(poi, info["d"], info["walk"], info["hs"], 0.0, {"bm25": bm25.score(query_tokens, i)}))

    if pool:
        max_bm = max(c.parts["bm25"] for c in pool) or 1.0
        for c in pool:
            cat = c.poi["category"]
            min_visit, _ = visit_range(cat)
            reach = max_reachable_distance_m(budget, min_visit, req.return_to_start, speed) or 1.0
            text_s = c.parts["bm25"] / max_bm
            # Earlier categories in the intent list are the more typical answers.
            if cat in target:
                cat_s = 1.0 - 0.5 * (target.index(cat) / max(1, len(target) - 1)) if len(target) > 1 else 1.0
            else:
                cat_s = 0.5  # a named place outside the requested types
            prox_s = max(0.0, 1.0 - c.distance_m / reach)
            bonus = 0.0
            tags = c.poi.get("osm_tags") or {}
            if "wifi" in unsupported and tags.get("internet_access") in ("wlan", "yes", "wifi"):
                bonus += 0.1
            if "wheelchair" in unsupported and tags.get("wheelchair") == "yes":
                bonus += 0.1
            if night and c.hours.status == "open":
                bonus += 0.1
            if harsh and is_indoor(cat):
                bonus += 0.15
            if c.poi.get("notable") and (notable_wanted or "sights" in intents):
                bonus += 0.2 if notable_wanted else 0.1
            if c.id in named_real:
                bonus += 0.6  # the user named this place
            c.parts.update(text=round(text_s, 3), category=round(cat_s, 3), proximity=round(prox_s, 3),
                           bonus=round(bonus, 2))
            c.score = round(0.45 * text_s + 0.35 * cat_s + 0.20 * prox_s + bonus, 4)
        pool.sort(key=lambda c: (-c.score, c.distance_m))

    mode, mode_note = "lexical", None
    if config.RETRIEVAL_MODE == "hybrid" and text and len(pool) > 1:
        from . import semantic
        try:
            pool = semantic.fuse(ds, text, pool)
            mode = "hybrid"
        except semantic.SemanticUnavailable as exc:
            mode_note = str(exc)
    chosen = _diverse(pool, k, [categories_for(g) if g else [] for g in req.groups])
    # Named destinations first (still only if they passed every hard filter above).
    for c in [c for c in pool if c.id in named_real][::-1]:
        if c not in chosen:
            chosen = [c] + chosen[: max(0, k - 1)]
    return RetrievalResult(lang=lang, query_lang=query_lang, intents=intents, assumed_intents=assumed,
                           target_categories=target, budget_min=budget, budget_source=budget_source,
                           unsupported=unsupported, night=night, candidates=chosen, excluded=dict(excluded),
                           considered=len(ds.pois), now=now, weather=req.weather, pool=pool, negated=negated,
                           named=sorted(named_real), mode=mode, mode_note=mode_note, named_excluded=named_excluded,
                           named_pois={i: ds.get(i) for i in named_real}, flight=mentions_flight(text),
                           timings_ms={"retrieval": round((_time.perf_counter() - t0) * 1000, 1)})


def _hard_filters(poi, req, target, negated, named_real, excluded_ids, budget, speed, now, octx):
    """(exclusion code or None, info). Every rule here is applied in code, never by the model."""
    from .itinerary import outdoor_single
    cat = poi["category"]
    if poi["id"] in excluded_ids or any(m in excluded_ids for m in poi.get("merged_ids", [])):
        return EXCL_USER, {}
    if cat in negated:
        return EXCL_NEGATED, {}
    if cat not in target and poi["id"] not in named_real:
        return EXCL_CATEGORY, {}
    if req.known_hours_only and not poi.get("opening_hours"):
        return EXCL_UNKNOWN_HOURS, {}
    if req.wheelchair_only and (poi.get("osm_tags") or {}).get("wheelchair") not in ("yes", "limited"):
        return EXCL_NO_WHEELCHAIR, {}
    d = haversine_m(req.lat, req.lon, poi["lat"], poi["lon"])
    min_visit, _ = visit_range(cat)
    walk = approx_walk_minutes(d, speed)
    info = {"distance_m": round(d), "walk_min": walk, "min_visit": min_visit}
    if d > max_reachable_distance_m(budget, min_visit, req.return_to_start, speed) or \
            (req.max_distance_m is not None and d >= req.max_distance_m):
        return EXCL_TOO_FAR, info
    if 2 * walk + min_visit > budget and req.return_to_start or walk + min_visit > budget:
        return EXCL_TOO_FAR, info
    hs = status_at(poi.get("opening_hours"), now)
    at_arrival = check_visit(poi.get("opening_hours"), now + timedelta(minutes=walk), min_visit)
    if at_arrival == "closed":
        return (EXCL_CLOSED if hs.status == "closed" else EXCL_CLOSES_SOON), info
    if req.outdoor_max is not None and outdoor_single(poi, walk, octx) > req.outdoor_max:
        return EXCL_OUTDOOR, info
    return None, {"d": d, "walk": walk, "hs": hs}


def chain_key(poi: dict) -> str:
    """Same name across scripts ("Кофе Бум" / "Coffee Boom") = same chain: one branch per plan."""
    from .translit import skeleton
    return skeleton(poi.get("name") or "") or (poi.get("name") or "").strip().lower()


def _diverse(pool: list[Candidate], k: int, group_cats: list[list[str]]) -> list[Candidate]:
    """Top-k with at most 2 per category and one place per name (no two branches of one chain);
    in group mode, take turns between participants first."""
    chosen: list[Candidate] = []
    per_cat = Counter()

    names: set[str] = set()

    def take(c: Candidate) -> bool:
        nm = chain_key(c.poi)
        if c in chosen or per_cat[c.poi["category"]] >= 2 or len(chosen) >= k or nm in names:
            return False  # also: two branches of the same brand are not offered together
        names.add(nm)
        chosen.append(c)
        per_cat[c.poi["category"]] += 1
        return True

    if any(group_cats):
        for _round in range(2):
            for cats in group_cats:
                for c in pool:
                    if (not cats or c.poi["category"] in cats) and c not in chosen and take(c):
                        break
    for c in pool:
        take(c)
    return chosen


def intent_labels(intents: list[str], lang: str) -> list[str]:
    return [INTENT_LABELS[i].get(lang, INTENT_LABELS[i]["en"]) for i in intents]


assert set(INTENTS) == set(INTENT_LABELS)
