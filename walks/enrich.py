"""Add photos and short descriptions to notable places, from free and open sources.

Sources (all free, no key):
  * Wikidata (CC0): label/description in kk/ru/en, main image (P18), Wikipedia article titles
  * Wikimedia Commons: image thumbnail URL, author and licence (shown under every photo)
  * Wikipedia (CC BY-SA): first sentences of the article in kk/ru/en, with a link
  * OpenStreetMap tags `wikimedia_commons` / `image` when they point to Wikimedia Commons

Only places that OpenStreetMap links to Wikidata/Commons get media. Nothing is invented:
no photo or description is added when the sources have none. Photos from other sites
(Google, 2GIS, Instagram...) are never used because their licence is unknown.
Results are written into data/pois.json under poi["media"] (atomic save).
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from urllib.parse import quote, unquote

import requests

from .osm_collect import save_atomic

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://{lang}.wikipedia.org/w/api.php"
LANGS = ("kk", "ru", "en")
SAFE_MEDIA = re.compile(r"^https://(upload\.wikimedia\.org|commons\.wikimedia\.org|[a-z]{2,3}\.wikipedia\.org|"
                        r"www\.wikidata\.org)/[^\s\"'<>]*$")
MAX_SUMMARY = 420
THUMB_WIDTH = 640


class EnrichError(RuntimeError):
    pass


def user_agent() -> str:
    """Wikimedia asks for a descriptive User-Agent; WIKI_CONTACT (your GitHub URL or e-mail) is optional."""
    contact = os.environ.get("WIKI_CONTACT", "").strip()
    base = "AstanaWalks-hackathon-prototype/1.0 (educational, non-commercial"
    return base + (f"; {contact})" if contact else ")") + " python-requests"


def safe_media_url(u) -> str | None:
    return u if isinstance(u, str) and SAFE_MEDIA.match(u) else None


def _qid(tags: dict) -> str | None:
    v = (tags or {}).get("wikidata") or (tags or {}).get("wikidata_resolved") or ""
    m = re.match(r"^\s*(Q\d+)", v)
    return m.group(1) if m else None


def _commons_file_from_tags(tags: dict) -> str | None:
    """Accept only Commons files: 'File:X.jpg' or an upload.wikimedia.org / commons URL."""
    for key in ("wikimedia_commons", "image"):
        v = (tags or {}).get(key) or ""
        if v.startswith("File:"):
            return v[5:]
        m = re.search(r"commons\.wikimedia\.org/wiki/File:([^?#]+)", v)
        if m:
            return unquote(m.group(1)).replace("_", " ")
        m = re.search(r"upload\.wikimedia\.org/wikipedia/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/?#]+)", v)
        if m:
            return unquote(m.group(1)).replace("_", " ")
    return None


def clean_text(s, limit: int) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:!?»)])", r"\1", s)
    if len(s) > limit:
        cut = s[:limit].rsplit(" ", 1)[0]
        s = cut.rstrip(",;:") + "…"
    return s


CACHE_TTL_S = 30 * 24 * 3600


class Client:
    """Polite GET client: descriptive User-Agent, retries with back-off, optional on-disk cache.

    The cache (data/cache/wikimedia_cache.json) stores successful API answers for 30 days so a
    re-run does not repeat hundreds of requests. Delete the file (or use --refresh) to refetch.
    """

    def __init__(self, session=None, sleep=time.sleep, log=print, timeout: float = 30,
                 cache_path: Path | None = None):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache: dict = {}
        self.cache_hits = 0
        if self.cache_path and self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.cache = {}
        self.s = session or requests.Session()
        try:
            self.s.headers.update({"User-Agent": user_agent()})
        except AttributeError:
            pass
        self.sleep, self.log, self.timeout = sleep, log, timeout

    def save_cache(self) -> None:
        if not self.cache_path:
            return
        now = time.time()
        keep = {k: v for k, v in self.cache.items() if now - v.get("t", 0) < CACHE_TTL_S}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.cache_path)

    def get(self, url: str, params: dict) -> dict:
        params = {**params, "format": "json", "formatversion": "2"}
        key = url + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        hit = self.cache.get(key) if self.cache_path else None
        if hit and time.time() - hit.get("t", 0) < CACHE_TTL_S:
            self.cache_hits += 1
            return hit["data"]
        data = self._get(url, params)
        if self.cache_path and isinstance(data, dict) and "error" not in data:
            self.cache[key] = {"t": time.time(), "data": data}
        return data

    def _get(self, url: str, params: dict) -> dict:
        last = None
        for attempt in (1, 2, 3):
            try:
                r = self.s.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                last = type(exc).__name__
                self.sleep(3 * attempt)
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    last = "not JSON"
                    break
            last = f"HTTP {r.status_code}"
            if r.status_code in (429, 500, 502, 503, 504):
                self.sleep(5 * attempt)
                continue
            break
        raise EnrichError(f"{url}: {last}")


def _batches(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def fetch_wikidata(client: Client, qids: list[str]) -> dict[str, dict]:
    """{qid: {"labels": {lang: str}, "descriptions": {lang: str}, "image": filename|None, "wiki": {lang: title}}}"""
    out = {}
    for batch in _batches(qids, 50):
        data = client.get(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(batch),
                                         "props": "labels|descriptions|claims|sitelinks",
                                         "languages": "|".join(LANGS),
                                         "sitefilter": "|".join(f"{l}wiki" for l in LANGS)})
        ents = data.get("entities") or {}
        for qid, e in ents.items():
            if not isinstance(e, dict) or "missing" in e:
                continue
            claims = e.get("claims") or {}
            instance_of = []
            for claim in claims.get("P31", []):
                v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, dict) and isinstance(v.get("id"), str):
                    instance_of.append(v["id"])
            coords = None
            for claim in claims.get("P625", []):
                v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, dict) and isinstance(v.get("latitude"), (int, float)):
                    coords = (float(v["latitude"]), float(v["longitude"]))
                    break
            image = None
            for claim in claims.get("P18", []):
                v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, str) and v:
                    image = v
                    break
            out[qid] = {
                "labels": {l: v.get("value") for l, v in (e.get("labels") or {}).items() if l in LANGS and v.get("value")},
                "descriptions": {l: v.get("value") for l, v in (e.get("descriptions") or {}).items()
                                 if l in LANGS and v.get("value")},
                "image": image,
                "instance_of": instance_of[:10],
                "coords": coords,
                "wiki": {s[:-4]: v.get("title") for s, v in (e.get("sitelinks") or {}).items()
                         if s[:-4] in LANGS and v.get("title")},
            }
        client.sleep(1)
    return out


def norm_file(f) -> str:
    """MediaWiki file title rules: no 'File:' prefix, spaces not underscores, first letter upper-case."""
    f = unquote(str(f or "")).replace("_", " ").strip()
    if f.lower().startswith("file:"):
        f = f[5:].strip()
    return f[:1].upper() + f[1:]


def _filepath_thumb(name: str) -> str:
    # Commons redirects this to a resized copy on upload.wikimedia.org.
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(name.replace(" ", "_")) + f"?width={THUMB_WIDTH}"


def fetch_commons(client: Client, files: list[str]) -> dict[str, dict]:
    """{normalized filename: {"thumb", "page", "author", "license", "license_url"}} — only complete entries.

    Follows API continuation (large metadata can be split over several responses) and logs why
    any photo was skipped, so a run with 0 photos explains itself.
    """
    out: dict[str, dict] = {}
    reasons: Counter = Counter()
    sample = None
    for batch in _batches(sorted({norm_file(f) for f in files if f}), 10):
        params = {"action": "query", "titles": "|".join("File:" + f for f in batch), "prop": "imageinfo",
                  "iiprop": "url|extmetadata", "iiurlwidth": THUMB_WIDTH, "redirects": 1}
        pages: dict[str, dict] = {}
        alias: dict[str, str] = {}
        cont: dict = {}
        for _ in range(10):
            data = client.get(COMMONS_API, {**params, **cont})
            if isinstance(data.get("error"), dict):
                reasons["api error: " + str(data["error"].get("code"))] += len(batch)
                break
            q = data.get("query") or {}
            for kind in ("normalized", "redirects"):
                for n in q.get(kind) or []:
                    alias[n.get("to")] = alias.get(n.get("from"), n.get("from"))
            for page in q.get("pages") or []:
                t = page.get("title")
                if t not in pages or page.get("imageinfo"):
                    pages[t] = page
            if isinstance(data.get("continue"), dict):
                cont = {k: v for k, v in data["continue"].items() if k != "continue"}
                cont["continue"] = data["continue"].get("continue", "")
                continue
            break
        returned = set()
        for t, page in pages.items():
            name = norm_file(t)
            returned.add(name)
            if t in alias:
                returned.add(norm_file(alias[t]))
            info = (page.get("imageinfo") or [None])[0]
            if page.get("missing") or page.get("invalid"):
                reasons["file not on Commons"] += 1
                continue
            if not info:
                reasons["no image info returned"] += 1
                sample = sample or page
                continue
            meta = info.get("extmetadata") or {}
            if (meta.get("NonFree") or {}).get("value") in ("true", True):
                reasons["not a free licence"] += 1
                continue
            lic = clean_text((meta.get("LicenseShortName") or {}).get("value"), 60)
            if not lic:
                reasons["no licence information"] += 1
                sample = sample or page
                continue
            thumb = safe_media_url(info.get("thumburl")) or safe_media_url(_filepath_thumb(name))
            page_url = safe_media_url(info.get("descriptionurl")) or \
                safe_media_url("https://commons.wikimedia.org/wiki/File:" + quote(name.replace(" ", "_")))
            if not (thumb and page_url):
                reasons["unsafe link"] += 1
                continue
            lic_url = (meta.get("LicenseUrl") or {}).get("value") or ""
            entry = {"thumb": thumb, "page": page_url,
                     "author": clean_text((meta.get("Artist") or {}).get("value"), 120) or None,
                     "license": lic, "license_url": lic_url[:200] if re.match(r"^https?://", lic_url) else None,
                     "source": "Wikimedia Commons"}
            out[name] = entry
            if t in alias:
                out[norm_file(alias[t])] = entry
        missing = [f for f in batch if f not in returned]
        if missing:
            reasons["not in the API answer"] += len(missing)
        client.sleep(1)
    usable = len({id(v) for v in out.values()})
    client.log(f"Wikimedia Commons: {usable} usable photos" +
               (f"; skipped: {', '.join(f'{k} ({v})' for k, v in reasons.items())}" if reasons else ""))
    if sample is not None and os.environ.get("WIKI_DEBUG"):
        client.log("Example of a skipped answer: " + json.dumps(sample, ensure_ascii=False)[:800])
    return out


def fetch_extracts(client: Client, lang: str, titles: list[str]) -> dict[str, str]:
    """{title: first sentences} from one Wikipedia language (plain text)."""
    out = {}
    for batch in _batches(titles, 20):
        data = client.get(WIKIPEDIA_API.format(lang=lang), {"action": "query", "prop": "extracts", "exintro": 1,
                                                            "explaintext": 1, "exsentences": 2, "exlimit": 20,
                                                            "redirects": 1, "titles": "|".join(batch)})
        q = data.get("query") or {}
        alias = {}
        for kind in ("normalized", "redirects"):
            for n in q.get(kind) or []:
                alias[n.get("to")] = alias.get(n.get("from"), n.get("from"))
        for page in q.get("pages") or []:
            text = clean_text(page.get("extract"), MAX_SUMMARY)
            if not text or page.get("missing"):
                continue
            t = page.get("title", "")
            out[t] = text
            if t in alias:
                out[alias[t]] = text
        client.sleep(1)
    return out


def resolve_wikipedia_tags(client: Client, pois: list[dict]) -> int:
    """Places with only an OSM `wikipedia` tag ("ru:Байтерек") get their Wikidata ID from Wikipedia.
    The ID is stored as osm_tags["wikidata_resolved"]; the OSM tags themselves are not changed."""
    wanted: dict[str, dict[str, list[dict]]] = {}
    for p in pois:
        tags = p.get("osm_tags") or {}
        if _qid(tags) or not tags.get("wikipedia"):
            continue
        m = re.match(r"^\s*([a-z]{2,3}):(.+)$", tags["wikipedia"])
        if m:
            wanted.setdefault(m.group(1), {}).setdefault(m.group(2).strip(), []).append(p)
    found = 0
    for lang, titles in wanted.items():
        for batch in _batches(sorted(titles), 20):
            try:
                data = client.get(WIKIPEDIA_API.format(lang=lang), {"action": "query", "prop": "pageprops",
                                                                    "ppprop": "wikibase_item", "redirects": 1,
                                                                    "titles": "|".join(batch)})
            except EnrichError as exc:
                client.log(f"Wikipedia ({lang}) lookup skipped: {exc}")
                break
            q = data.get("query") or {}
            alias = {}
            for kind in ("normalized", "redirects"):
                for n in q.get(kind) or []:
                    alias[n.get("to")] = alias.get(n.get("from"), n.get("from"))
            for page in q.get("pages") or []:
                qid = (page.get("pageprops") or {}).get("wikibase_item")
                if not qid or not re.match(r"^Q\d+$", qid):
                    continue
                for t in {page.get("title"), alias.get(page.get("title"))}:
                    for p in titles.get(t, []):
                        p["osm_tags"]["wikidata_resolved"] = qid
                        found += 1
            client.sleep(1)
    if found:
        client.log(f"Wikidata IDs found via Wikipedia tags: {found}")
    return found


# Wikidata items that are clearly NOT a place: a person (the namesake of a street or monument),
# a family name, a given name, a Wikimedia disambiguation page.
NOT_A_PLACE = {"Q5", "Q101352", "Q202444", "Q4167410", "Q12308941", "Q11879590"}
MAX_IDENTITY_DISTANCE_M = 2000


def identity_check(poi: dict, info: dict) -> dict:
    """Is this Wikidata item the PLACE itself (not its namesake, operator or another institution)?

    ok         – a place-like item whose coordinates are within 2 km of the OSM record;
    no_coords  – the item has no coordinates: photo/description may be used (OSM links it to the
                 place), but its label is NOT used as the place's name;
    not_place  – a person, a name or a disambiguation page: nothing is used;
    far        – coordinates far from the OSM record: nothing is used.
    """
    from .geo import haversine_m
    if not info:
        return {"status": "missing"}
    if set(info.get("instance_of") or []) & NOT_A_PLACE:
        return {"status": "not_place"}
    c = info.get("coords")
    if not c:
        return {"status": "no_coords"}
    d = haversine_m(poi["lat"], poi["lon"], c[0], c[1])
    return {"status": "ok" if d <= MAX_IDENTITY_DISTANCE_M else "far", "distance_m": round(d)}


def enrich_pois(pois: list[dict], client: Client) -> dict:
    """Mutates pois in place (adds poi["media"]). Returns counts."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    resolve_wikipedia_tags(client, pois)
    qids = sorted({q for p in pois if (q := _qid(p.get("osm_tags")))})
    client.log(f"Places linked to Wikidata: {len(qids)}")
    wd = fetch_wikidata(client, qids) if qids else {}

    files = set()
    for p in pois:
        f = _commons_file_from_tags(p.get("osm_tags"))
        q = _qid(p.get("osm_tags"))
        if f:
            files.add(f)
        elif q and wd.get(q, {}).get("image"):
            files.add(wd[q]["image"])
    client.log(f"Photos to look up on Wikimedia Commons: {len(files)}")
    commons = fetch_commons(client, sorted(files)) if files else {}

    extracts: dict[str, dict[str, str]] = {}
    for lang in LANGS:
        titles = sorted({wd[q]["wiki"][lang] for q in wd if lang in wd[q]["wiki"]})
        if titles:
            try:
                extracts[lang] = fetch_extracts(client, lang, titles)
            except EnrichError as exc:
                client.log(f"Wikipedia ({lang}) skipped: {exc}")

    photos = descs = 0
    identity = Counter()
    for p in pois:
        q = _qid(p.get("osm_tags"))
        info = wd.get(q, {}) if q else {}
        ident = {**identity_check(p, info), "qid": q} if q else None
        if ident:
            identity[ident["status"]] += 1
        usable = bool(ident) and ident["status"] in ("ok", "no_coords")
        if not usable:
            info = {}
        f = _commons_file_from_tags(p.get("osm_tags")) or info.get("image")
        media: dict = {}
        photo = commons.get(norm_file(f)) if f else None
        if photo:
            media["photo"] = photo
        summary = {}
        for lang in LANGS:
            title = (info.get("wiki") or {}).get(lang)
            text = extracts.get(lang, {}).get(title) if title else None
            if text:
                summary[lang] = {"text": text, "source": "Wikipedia",
                                 "url": f"https://{lang}.wikipedia.org/wiki/" + title.replace(" ", "_")}
            elif info.get("descriptions", {}).get(lang):
                summary[lang] = {"text": clean_text(info["descriptions"][lang], 200), "source": "Wikidata",
                                 "url": f"https://www.wikidata.org/wiki/{q}"}
        if summary:
            media["summary"] = summary
        # Wikidata labels are stored separately with the identity result; walks/names.py shows them
        # only when the identity check is "ok". They never become OSM-style name:xx values.
        if info.get("labels"):
            media["labels"] = {k: clean_text(v, 160) for k, v in info["labels"].items()}
        if ident and ident["status"] != "missing":
            media["identity"] = ident
        if media:
            media["enriched_at"] = now
            p["media"] = media
            photos += "photo" in media
            descs += "summary" in media
        elif "media" in p:
            p.pop("media")
    if identity:
        client.log("Wikidata identity checks: " + ", ".join(f"{k} {v}" for k, v in sorted(identity.items())))
    return {"linked": len(qids), "photos": photos, "descriptions": descs, "identity": dict(identity)}


def enrich_file(path: Path, client: Client | None = None, refresh: bool = False) -> dict:
    path = Path(path)
    if not path.exists():
        raise EnrichError(f"{path} not found. Collect the data first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("meta", {}).get("is_synthetic"):
        raise EnrichError("Refusing to enrich a SYNTHETIC dataset.")
    if client is None:
        from . import config
        client = Client(cache_path=None if refresh else config.CACHE_DIR / "wikimedia_cache.json")
    try:
        stats = enrich_pois(data.get("pois", []), client)
    finally:
        client.save_cache()  # keep what was fetched even if a later step failed
    if client.cache_hits:
        client.log(f"Answers reused from the local cache: {client.cache_hits}")
    data.setdefault("meta", {})["media"] = {**stats, "enriched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                                            "sources": "Wikidata (CC0), Wikimedia Commons (per-file licences), Wikipedia (CC BY-SA)"}
    save_atomic(data, path)
    return stats
