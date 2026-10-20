"""Astana Walks — local web server (Python standard library only).

Run (PowerShell):   .venv\\Scripts\\python server.py
Then open:          http://localhost:8501

Endpoints
  GET  /                 the web app (web/index.html)
  GET  /assets/<file>    CSS / JS
  GET  /api/meta         dataset info, landmarks (names in kk/ru/en), labels, model status
  GET  /api/status       model status only
  GET  /api/places?q=    search the collected places by any name (start picker); dataset only
  GET  /api/gallery      places with a licensed photo + the date-based "place of the day"
  POST /api/recommend    plan from text/interests, or "surprise" mode; returns the canonical plan
  POST /api/replace      replace one stop of the current plan, keep the others
  POST /api/replan       recompute the plan for given stops (e.g. after removing one)

Common request fields (all optional except start):
  text, lang, start{type: landmark|coords|geo, id|lat,lon}, budget, back, interests[], weather,
  pace (leisurely|normal|brisk), deadline{enabled, at "YYYY-MM-DDTHH:MM", buffer_min},
  outdoor{max_min, strict}, group{participants[{interests, minutes, pace}]},
  exclude{visited[], unavailable[], other[]}
Privacy: request bodies (which contain start coordinates) are never logged or stored.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from walks import config, llm, semantic, weather
from walks.categories import LANGS, all_labels
from walks.constraints import ConstraintError, resolve
from walks.data import DatasetError, load_dataset, start_landmarks
from walks.names import display_names
from walks.geo import haversine_m
from walks.search import find_mentions, index_for, strip_case
from walks.geo import PACES, InvalidCoordinates, validate_coords
from walks.pipeline import run, run_app_choice, run_replace, run_replan, run_surprise, to_dict
from walks.retrieval import EmptyRequest, Request
from walks.text import INTENT_LABELS, UNSUPPORTED_LABELS

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_BODY = 64 * 1024
MAX_TEXT = 500
REPLACE_REASONS = ("replace", "visited", "closed", "too_far")

_ds_lock = threading.Lock()
_ds_cache: dict = {"mtime": None, "ds": None}


def CLOCK() -> datetime:  # tests replace this with a fixed clock
    return datetime.now(config.ASTANA_TZ)


def get_dataset():
    path = config.DATA_PATH
    mtime = path.stat().st_mtime if path.exists() else None
    with _ds_lock:
        if _ds_cache["ds"] is None or _ds_cache["mtime"] != mtime or _ds_cache.get("path") != str(path):
            _ds_cache["ds"] = load_dataset(path)  # raises DatasetError
            _ds_cache["mtime"] = mtime
            _ds_cache["path"] = str(path)
        return _ds_cache["ds"]


def dataset_center(ds) -> tuple[float, float]:
    c = (ds.meta.get("areas") or [{}])[0].get("center") or ds.meta.get("center")
    if c and "lat" in c:
        return float(c["lat"]), float(c["lon"])
    return ds.pois[0]["lat"], ds.pois[0]["lon"]


def coverage(ds) -> list[dict]:
    """Collected areas, for the map: circles (area runs) and the citywide box (landmarks run)."""
    out = []
    for a in ds.meta.get("areas") or []:
        c = a.get("center") or {}
        if a.get("kind") == "landmarks":
            from walks.osm_collect import ASTANA_BBOX_SWNE
            out.append({"kind": "landmarks", "bbox": list(ASTANA_BBOX_SWNE)})
        elif "lat" in c and a.get("radius_m"):
            out.append({"kind": "area", "lat": c["lat"], "lon": c["lon"], "radius_m": a["radius_m"]})
    return out


def labels_payload() -> dict:
    return {"categories": all_labels(), "intents": INTENT_LABELS, "unsupported": UNSUPPORTED_LABELS,
            "paces": {k: v for k, v in PACES.items()}, "detour_factor": config.ROUTE_DETOUR_FACTOR}


def meta_payload() -> dict:
    try:
        ds = get_dataset()
    except DatasetError as exc:
        return {"dataset": None, "dataset_error": str(exc), "provider": llm.status(),
                "labels": labels_payload(), "landmarks": []}
    m = ds.meta
    landmarks = [place_brief(p, group) for p, group in start_landmarks(ds, limit=60, grouped=True)]
    return {
        "dataset": {"count": len(ds.pois), "source": m.get("source"), "license": m.get("license"),
                    "collected_at": m.get("collected_at"), "is_synthetic": ds.is_synthetic,
                    "areas": len(m.get("areas") or [1]), "merged_duplicates": ds.merged,
                    "notable_count": sum(1 for p in ds.pois if p.get("notable")),
                    "counts_by_category": m.get("counts_by_category")},
        "landmarks": landmarks,
        "center": dict(zip(("lat", "lon"), dataset_center(ds))),
        "coverage": coverage(ds),
        "retrieval": semantic.status(),
        "provider": llm.status(),
        "weather_enabled": config.WEATHER_ENABLED,
        "labels": labels_payload(),
        "now": CLOCK().strftime("%Y-%m-%dT%H:%M"),
    }


def place_brief(p: dict, group: str | None = None) -> dict:
    """What the start picker needs: names in all languages with provenance, type, address, position."""
    tags = p.get("osm_tags") or {}
    dn = display_names(p)
    return {"id": p["id"], "display_names": dn, "names": {k: v["text"] for k, v in dn.items()},
            "category": p["category"], "notable": bool(p.get("notable")), "group": group,
            "address": " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x) or None,
            "lat": p["lat"], "lon": p["lon"]}


def gallery() -> tuple[int, dict]:
    """GET /api/gallery — places that have a free-licensed photo (Wikimedia, author + licence), and
    the "place of the day": picked by today's date (Astana time) from those places, the same for
    everyone all day. A date-based pick, not a ranking or a popularity claim."""
    import hashlib
    from walks.pipeline import public_media
    try:
        ds = get_dataset()
    except DatasetError as exc:
        return _err(503, "no_dataset", str(exc))
    items = []
    for p in ds.pois:
        m = public_media(p)
        if m and m.get("photo") and not p.get("name_is_generated"):
            items.append({**place_brief(p), "media": m})
    items.sort(key=lambda x: x["id"])
    today = CLOCK().strftime("%Y-%m-%d")
    day = None
    if items:
        idx = int(hashlib.sha1(today.encode()).hexdigest(), 16) % len(items)
        day = items[idx]
    return 200, {"date": today, "day": day, "items": items[:60], "count": len(items)}


def places(query: str) -> tuple[int, dict]:
    """GET /api/places?q=... — search the collected dataset only (no geocoder)."""
    try:
        ds = get_dataset()
    except DatasetError as exc:
        return _err(503, "no_dataset", str(exc))
    q = (query or "").strip()[:80]
    idx = index_for(ds)
    hits = idx.search(q, limit=15) if q else []
    if q and not hits:  # "Байтерека", "Хан Шатыра": try the word without a case ending
        words = q.split()
        for stem in strip_case(words[-1].lower()):
            hits = idx.search(" ".join(words[:-1] + [stem]), limit=15)
            if hits:
                break
    return 200, {"query": q, "results": [{**place_brief(p), "score": sc} for p, sc in hits],
                 "searched": len(ds.pois)}


def parse_start(ds, start: dict) -> tuple[float, float, str, str, str | None]:
    if not isinstance(start, dict):
        raise InvalidCoordinates("Missing start point.")
    kind = start.get("type")
    if kind == "landmark":
        poi = ds.get(str(start.get("id")))
        if not poi:
            raise InvalidCoordinates("Unknown landmark.")
        return poi["lat"], poi["lon"], poi["name"], "landmark", poi["id"]
    if kind in ("coords", "geo"):
        lat, lon = validate_coords(start.get("lat"), start.get("lon"))
        return lat, lon, "", kind, None
    raise InvalidCoordinates("Unknown start type.")


def _err(status: int, code: str, detail: str = "", **params) -> tuple[int, dict]:
    return status, {"error": {"code": code, "detail": detail, "params": params}}


CONFLICT_M = 400   # a named start place farther than this from the selected start is a conflict


def _mentions(ds, text: str, start: dict, body: dict) -> tuple[list[str], dict | None]:
    """(named destination IDs, clarification or None). A place named with a location word
    ("near Baiterek", "от Байтерека", "Бәйтерек маңында") that is far from the selected start is a
    conflict: we ask once instead of silently planning from the wrong place."""
    if not text or body.get("start_choice") == "keep":
        ms = [m for m in find_mentions(ds, text)] if text else []
        return [m["poi"]["id"] for m in ms if not m["cue"] and m["score"] >= 80
                and m["poi"]["id"] != start.get("landmark_id")][:2], None
    ms = find_mentions(ds, text)
    cue = [m for m in ms if m["cue"]]
    named = [m["poi"]["id"] for m in ms if not m["cue"] and m["score"] >= 80
             and m["poi"]["id"] != start.get("landmark_id")][:2]
    if not cue:
        return named, None
    top = cue[0]["score"]
    best = [m for m in cue if m["score"] == top]
    near = [m for m in best if m["poi"]["id"] == start.get("landmark_id") or
            haversine_m(start["lat"], start["lon"], m["poi"]["lat"], m["poi"]["lon"]) <= CONFLICT_M]
    if near:
        return named, None
    selected = {"kind": start["kind"], "display_names": start.get("display_names")}
    options = [place_brief(m["poi"]) for m in best[:3]]
    code = "start_ambiguous" if len(best) > 1 else "start_conflict"
    return named, {"code": code, "phrase": best[0]["phrase"], "options": options, "selected": selected}


def _return_point(ds, raw) -> tuple[float, float, str] | None:
    """Active walk: the original start, sent back by the page. Validated like any start."""
    if raw in (None, {}):
        return None
    if not isinstance(raw, dict):
        raise InvalidCoordinates("Bad return point.")
    if raw.get("type") == "landmark":
        poi = ds.get(str(raw.get("id")))
        if not poi:
            raise InvalidCoordinates("Unknown landmark.")
        return poi["lat"], poi["lon"], poi["name"]
    lat, lon = validate_coords(raw.get("lat"), raw.get("lon"))
    return lat, lon, ""


def _prepare(body: dict, use_mentions: bool = False):
    """Validate everything shared by all planning endpoints. Returns (ctx, None) or (None, error)."""
    try:
        ds = get_dataset()
    except DatasetError as exc:
        return None, _err(503, "no_dataset", str(exc))
    lang = body.get("lang") if body.get("lang") in LANGS else "en"
    if not isinstance(body.get("text", ""), (str, type(None))):
        return None, _err(400, "bad_request")
    text = str(body.get("text") or "")[:MAX_TEXT]
    try:
        lat, lon, start_name, start_kind, landmark_id = parse_start(ds, body.get("start"))
    except InvalidCoordinates as exc:
        code = "outside_astana" if "Astana" in str(exc) else "bad_coords"
        return None, _err(400, code, str(exc))
    now = CLOCK()
    try:
        cons = resolve({**body, "text": text}, now)
    except ConstraintError as exc:
        return None, _err(400, exc.code, "", **exc.params)
    wx = None
    if body.get("weather", True) and config.WEATHER_ENABLED:
        wx = weather.current(*dataset_center(ds))
    exclude = set(cons.excluded_ids)
    if landmark_id:
        exclude.add(landmark_id)
    groups = [p.interests for p in cons.participants]
    try:
        ret = _return_point(ds, body.get("return_to"))
    except InvalidCoordinates as exc:
        return None, _err(400, "bad_coords", str(exc))
    req = Request(text=text, lat=lat, lon=lon, budget_min=cons.budget_min, return_to_start=cons.return_to_start,
                  interests=list(cons.interests if not groups else []), now=now, answer_lang=lang, weather=wx,
                  exclude_ids=tuple(exclude), speed=cons.speed, outdoor_max=cons.outdoor_max,
                  outdoor_strict=cons.outdoor_strict, groups=groups, budget_fixed=True,
                  known_hours_only=cons.filters["known_hours"], wheelchair_only=cons.filters["wheelchair"],
                  broaden=cons.broaden)
    if ret:
        req.return_lat, req.return_lon, req.return_name = ret
    start = {"lat": lat, "lon": lon, "name": start_name, "kind": start_kind, "landmark_id": landmark_id,
             "back": cons.return_to_start,
             "display_names": display_names(ds.get(landmark_id)) if landmark_id else None,
             "names": ({k: v["text"] for k, v in display_names(ds.get(landmark_id)).items()}
                       if landmark_id else None)}
    clarify = None
    if use_mentions:
        named, clarify = _mentions(ds, text, start, body)
        req.named_ids = tuple(named)
    return {"ds": ds, "cons": cons, "req": req, "start": start, "start_name": start_name or "Start",
            "clarify": clarify}, None


def _plan_stops(ds, raw) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        raise ConstraintError("bad_plan")
    out, seen = [], set()
    for s in raw:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not ds.get(s["id"]):
            raise ConstraintError("bad_plan")
        real = ds.get(s["id"])["id"]
        if real in seen:
            raise ConstraintError("bad_plan")
        seen.add(real)
        try:
            vm = int(s.get("visit_minutes"))
        except (TypeError, ValueError):
            raise ConstraintError("bad_plan") from None
        if not 1 <= vm <= 300:
            raise ConstraintError("bad_plan")
        out.append({"id": real, "visit_minutes": vm})
    return out


def _respond(prep: dict, res) -> tuple[int, dict]:
    cons = prep["cons"].to_dict()
    payload = to_dict(res, prep["start"], cons)
    return 200, payload


def recommend(body: dict, llm_call=None) -> tuple[int, dict]:
    prep, err = _prepare(body, use_mentions=body.get("mode", "ask") == "ask")
    if err:
        return err
    if prep["clarify"]:
        # One concise question with selectable answers; nothing is planned from the wrong place.
        return 200, {"clarify": prep["clarify"], "start": prep["start"], "plan": None,
                     "constraints": prep["cons"].to_dict()}
    kwargs = {"llm_call": llm_call} if llm_call else {}
    mode = body.get("mode", "ask")
    if mode not in ("ask", "surprise"):
        return _err(400, "bad_request")
    if mode == "surprise":
        s = body.get("surprise") or {}
        try:
            seed = int(s.get("seed", 0))
        except (TypeError, ValueError):
            return _err(400, "bad_request")
        avoid = s.get("avoid") or []
        if not isinstance(avoid, list) or len(avoid) > 50 or any(
                not isinstance(a, list) or len(a) > 3 or not all(isinstance(x, str) for x in a) for a in avoid):
            return _err(400, "bad_request")
        res = run_surprise(prep["ds"], prep["req"], prep["start_name"], seed, avoid,
                           deadline=prep["cons"].deadline is not None, **kwargs)
        return _respond(prep, res)
    if body.get("no_model") is True:
        # Explicit user choice after a model failure: deterministic, labelled, same constraints.
        try:
            res = run_app_choice(prep["ds"], prep["req"], prep["start_name"], deadline=prep["cons"].deadline is not None)
        except EmptyRequest as exc:
            return _err(400, exc.code, str(exc))
        return _respond(prep, res)
    try:
        res = run(prep["ds"], prep["req"], start_name=prep["start_name"],
                  deadline=prep["cons"].deadline is not None, **kwargs)
    except EmptyRequest as exc:
        return _err(400, exc.code, str(exc))
    return _respond(prep, res)


def replace(body: dict, llm_call=None) -> tuple[int, dict]:
    prep, err = _prepare(body)
    if err:
        return err
    try:
        stops = _plan_stops(prep["ds"], body.get("plan_stops"))
    except ConstraintError as exc:
        return _err(400, exc.code)
    target = body.get("target")
    reason = body.get("reason", "replace")
    tpoi = prep["ds"].get(str(target)) if isinstance(target, str) else None
    if not tpoi or tpoi["id"] not in {s["id"] for s in stops} or reason not in REPLACE_REASONS:
        return _err(400, "bad_plan")
    kwargs = {"llm_call": llm_call} if llm_call else {}
    req = prep["req"]
    req.exclude_ids = tuple(set(req.exclude_ids) | {s["id"] for s in stops})
    res = run_replace(prep["ds"], req, prep["start_name"], stops, tpoi["id"], reason, **kwargs)
    return _respond(prep, res)


def replan(body: dict, llm_call=None) -> tuple[int, dict]:
    """Recompute a plan for given stops: after removing a stop, switching to a plan style
    (explain=true: new stops get a short model explanation), or during an active walk
    ("I'm here": start = current position, return_to = the original start)."""
    prep, err = _prepare(body)
    if err:
        return err
    try:
        stops = _plan_stops(prep["ds"], body.get("plan_stops"))
    except ConstraintError as exc:
        return _err(400, exc.code)
    explain = body.get("explain") is True
    keep = body.get("keep_ids") or []
    if not isinstance(keep, list) or not all(isinstance(x, str) for x in keep):
        return _err(400, "bad_plan")
    model = (llm_call or llm.generate) if explain else None
    res = run_replan(prep["ds"], prep["req"], prep["start_name"], stops, llm_call=model, keep_ids=tuple(keep),
                     deadline=prep["cons"].deadline is not None)
    return _respond(prep, res)


class Handler(BaseHTTPRequestHandler):
    server_version = "AstanaWalks/3"
    llm_call = None  # tests may inject a fake model

    def log_message(self, fmt, *args):  # never log bodies; path only
        print(f"{self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, status: int, payload: bytes, ctype: str, cache: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        # OpenStreetMap's tile servers block requests without a Referer, so send the origin only
        # (e.g. "http://localhost:8501") — never paths or query strings.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "max-age=300" if cache else "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: dict):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._file(WEB_DIR / "index.html")
        if path.startswith("/assets/"):
            target = (WEB_DIR / path.lstrip("/")).resolve()
            if WEB_DIR.resolve() not in target.parents:
                return self._json(404, {"error": {"code": "not_found"}})
            return self._file(target)
        if path == "/api/meta":
            return self._json(200, meta_payload())
        if path == "/api/status":
            return self._json(200, llm.status())
        if path == "/api/gallery":
            return self._json(*gallery())
        if path == "/api/places":
            from urllib.parse import parse_qs, urlparse
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0]
            return self._json(*places(q))
        self._json(404, {"error": {"code": "not_found"}})

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = {"/api/recommend": lambda b: recommend(b, llm_call=type(self).llm_call),
                  "/api/replace": lambda b: replace(b, llm_call=type(self).llm_call),
                  "/api/replan": lambda b: replan(b, llm_call=type(self).llm_call)}
        if path not in routes:
            return self._json(404, {"error": {"code": "not_found"}})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._json(400, {"error": {"code": "bad_request"}})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": {"code": "bad_request"}})
        try:
            status, payload = routes[path](body)
        except Exception as exc:  # never leak a traceback to the page
            print(f"Internal error on {path}: {type(exc).__name__}: {exc}")
            status, payload = 500, {"error": {"code": "internal", "detail": type(exc).__name__}}
        self._json(status, payload)

    def _file(self, p: Path, cache: bool = False):
        if not p.is_file():
            return self._json(404, {"error": {"code": "not_found"}})
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype, cache)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    ap = argparse.ArgumentParser(description="Astana Walks local server")
    ap.add_argument("--host", default=config.HOST)
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    srv = make_server(args.host, args.port)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    st = llm.status()
    print(f"Astana Walks running at {url}  (Ctrl+C to stop)")
    print(f"Model: {st['detail']}")
    print(f"Retrieval: {semantic.status()['detail']}")
    try:
        ds = get_dataset()
        extra = f", {ds.merged} duplicates merged" if ds.merged else ""
        print(f"Dataset: {len(ds.pois)} places{extra}{' (SYNTHETIC TEST DATA)' if ds.is_synthetic else ''}")
    except DatasetError as exc:
        print(f"Dataset: {exc}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
