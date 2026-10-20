"""Evaluate Astana Walks on eval/queries.json and write measured results (nothing is estimated).

Usage (PowerShell, from the project folder):
  # retrieval / planning / constraint metrics only (no model calls; fast, deterministic)
  .venv\\Scripts\\python eval\\run_eval.py
  # also call the configured local model (Ollama) for every query: ID validity, JSON errors, removed claims, latency
  .venv\\Scripts\\python eval\\run_eval.py --live
  # compare lexical and hybrid retrieval on the same queries (needs requirements-semantic.txt)
  .venv\\Scripts\\python eval\\run_eval.py --mode both
Options: --data <pois.json> (default data/pois.json), --now 2026-10-21T14:30 (Astana time; fixed for repeatability)

Without --live, a deterministic NO-MODEL selector picks evidence P1..P3 with neutral text: that measures the
code (retrieval, filters, itinerary), never language quality. Results: eval/results/<name>.json and .md, plus
to_label.csv with the top-5 candidates per query for POI-level labelling against YOUR data snapshot
(save it as eval/labels.csv with a 'relevant' column of 1/0, then re-run to get POI-level Hit@5).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from walks import config, llm  # noqa: E402
from walks.data import load_dataset  # noqa: E402
from walks.llm import LLMReply  # noqa: E402
from walks.search import index_for  # noqa: E402


def no_model(system: str, user: str) -> LLMReply:
    """Deterministic stand-in: selects the first three evidence IDs (or explains all). NOT a model."""
    ids = re.findall(r'"id":\s*"(P\d+)"', user)
    if "already chosen" not in system:
        ids = ids[:3]
    return LLMReply(json.dumps({"recommendations": [{"id": i, "why": "", "activity": "", "visit_minutes": 20} for i in ids]}),
                    "none", "no-model", 0.0)


class Timed:
    """Wraps the real model call to record per-call latency (first call = warm-up incl. model loading)."""
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, system, user, schema=None):
        t0 = time.perf_counter()
        try:
            return llm.generate(system, user, schema=schema)
        finally:
            self.calls.append(time.perf_counter() - t0)


# Documented SIMULATED start points, used only when the named place is not in the evaluated
# dataset (approximate public coordinates; the row then says it was a simulated point, and it does
# NOT validate the named landmark itself). The app never substitutes a start: it asks the user.
SIMULATED_STARTS = {
    "expo": (51.0890, 71.4160, "EXPO / Astana IT University area (the collector's default centre)"),
    "baiterek": (51.1283, 71.4305, "Baiterek tower area"),
    "khan shatyr": (51.1323, 71.4036, "Khan Shatyr area"),
    "mega silk way": (51.0889, 71.4115, "Mega Silk Way area"),
}
ALIASES = {"бәйтерек": "baiterek", "байтерек": "baiterek", "хан шатыр": "khan shatyr", "экспо": "expo"}


def resolve_start(ds, name: str):
    """(start body, description, kind). kind: "named" (a dataset place, exact or near-exact name match)
    or "simulated" (documented coordinates; no place was substituted for it)."""
    hits = index_for(ds).search(name, limit=1) if name else []
    if hits and hits[0][1] >= 85:
        return {"type": "landmark", "id": hits[0][0]["id"]}, hits[0][0]["name"], "named"
    key = ALIASES.get((name or "").strip().lower(), (name or "").strip().lower())
    if key in SIMULATED_STARTS:
        lat, lon, label = SIMULATED_STARTS[key]
        return {"type": "coords", "lat": lat, "lon": lon}, f"SIMULATED point: {label} ({lat}, {lon})", "simulated"
    raise SystemExit(f"Start '{name}' is neither in the dataset nor in SIMULATED_STARTS: add explicit coordinates.")


def body_for(q: dict, start: dict, now: datetime) -> dict:
    b = {"text": q.get("text", ""), "lang": q["lang"], "start": start, "budget": q.get("budget", 60), "back": True,
         "weather": False, "pace": q.get("pace", "normal"), "filters": q.get("filters") or {}}
    if q.get("outdoor_max") is not None:
        b["outdoor"] = {"max_min": q["outdoor_max"]}
    if q.get("group"):
        b["group"] = {"participants": [{"interests": g, "minutes": q.get("budget", 60), "pace": q.get("pace", "normal")} for g in q["group"]]}
    if q.get("deadline_in_min"):
        at = now + timedelta(minutes=q["deadline_in_min"])
        b["deadline"] = {"enabled": True, "at": at.strftime("%Y-%m-%dT%H:%M"), "buffer_min": q.get("buffer", 10)}
    return b


def evaluate(ds, queries, model, now, labels):
    server.CLOCK = lambda: now
    rows = []
    for q in queries:
        start, start_used, start_kind = resolve_start(ds, q.get("start", ""))
        qnow = now
        if q.get("time"):   # scenario-specific clock, e.g. a late-night request at 23:30
            hh, mm = map(int, q["time"].split(":"))
            qnow = now.replace(hour=hh, minute=mm)
        server.CLOCK = lambda t=qnow: t
        b = body_for(q, start, qnow)
        t0 = time.perf_counter()
        st, r = server.recommend(b, llm_call=model)
        elapsed = time.perf_counter() - t0
        e = q.get("expect", {})
        row = {"id": q["id"], "lang": q["lang"], "tags": q.get("tags", []), "start_used": start_used,
               "planning_time": qnow.strftime("%H:%M"),
               "start_kind": start_kind, "status": st, "seconds_total": round(elapsed, 3)}
        if r.get("clarify"):
            row["clarify"] = r["clarify"]["code"]
        # "start" = any one start question (conflict or ambiguous name); an unexpected question is a failure
        got, want = row.get("clarify"), e.get("clarify")
        row["clarify_ok"] = (bool(got) and got.startswith(want)) if want else (False if got else None)
        cands = [c["poi"] for c in (r.get("trace") or {}).get("candidates", [])][:5]
        row["top5"] = [{"id": p["id"], "name": p["name"], "category": p["category"]} for p in cands]
        plan = r.get("plan")
        stops = plan["stops"] if plan else []
        row["plan"] = [{"id": s["id"], "category": s["poi"]["category"]} for s in stops]
        # --- retrieval (category labels)
        if e.get("categories_any") and not row.get("clarify"):
            row["hit5_category"] = any(p["category"] in e["categories_any"] for p in cands) if cands else False
            if not cands:
                # Evidence for "legitimately unavailable": how many places of the expected types exist at
                # all and pass the source filters (ignoring distance/time), and what the code excluded.
                flt = q.get("filters") or {}
                avail = [p for p in ds.pois if p["category"] in e["categories_any"]
                         and (not flt.get("wheelchair") or (p.get("osm_tags") or {}).get("wheelchair") in ("yes", "limited"))
                         and (not flt.get("known_hours") or p.get("opening_hours"))]
                row["expected_type_in_dataset_passing_filters"] = len(avail)
                row["excluded_by_code"] = (r.get("trace") or {}).get("excluded")
                if q.get("no_plan_ok") and (not avail or set((row["excluded_by_code"] or {})) & {"no_wheelchair_info", "unknown_hours", "outdoor"}):
                    row["hit5_category"] = None
                    row["hit5_na_reason"] = "hard filter left no eligible place (see excluded_by_code)"
        if e.get("named"):
            named = [p["id"] for p, sc in index_for(ds).search(e["named"], limit=3) if sc >= 75]
            row["named_in_dataset"] = bool(named)
            excl = {n["id"]: n["reason"] for n in (r.get("understood") or {}).get("named_excluded", [])}
            row["named_excluded"] = {i: excl[i] for i in named if i in excl}
            reachable = [i for i in named if i not in excl]
            # Hit@5 only counts named places that passed the hard filters; the others must be EXPLAINED.
            row["hit5_named"] = any(p["id"] in reachable for p in cands) if reachable else None
            row["named_unreachable_explained"] = bool(row["named_excluded"]) if named and not reachable else None
        if labels.get(q["id"]):
            rel = labels[q["id"]]
            row["hit5_poi"] = any(rel.get(p["id"]) for p in cands)
            row["precision5_poi"] = sum(1 for p in cands if rel.get(p["id"])) / max(1, len(cands))
        # --- hard constraints
        viol = []
        if plan:
            if plan["total_min"] > plan["budget_min"]:
                viol.append("over_budget")
            if any(s["poi"]["category"] in e.get("categories_none", []) for s in stops):
                viol.append("negated_category_in_plan")
            if q.get("outdoor_max") is not None and plan["outdoor_min"] > q["outdoor_max"]:
                viol.append("outdoor_cap")
            if r["constraints"].get("deadline") and plan["total_min"] > r["constraints"]["deadline"]["cap_min"]:
                viol.append("deadline")
            if any(s["hours_at_arrival"] == "closed" for s in stops):
                viol.append("closed_at_arrival")
        if any(p["category"] in e.get("categories_none", []) for p in cands):
            viol.append("negated_category_in_candidates")
        row["violations"] = viol
        # --- unknowns, empty results
        if e.get("unknown"):
            row["unknown_reported"] = set(e["unknown"]) <= set((r.get("understood") or {}).get("unsupported", []))
        if not plan and not row.get("clarify"):
            row["empty"] = True
            row["suggestions"] = [s["key"] for s in r.get("suggestions", [])]
            err = (r.get("error") or {}).get("code")
            row["empty_kind"] = ("model_failure" if (err or r.get("note_code") == "model_empty") else "no_feasible_place")
        tok = (r.get("trace") or {}).get("model_tokens")
        if tok and any(v is not None for v in tok.values()):
            row["model_tokens"] = tok
        if e.get("notice"):
            row["notice_ok"] = bool((r.get("understood") or {}).get(e["notice"]))
        # --- model output (meaningful only with --live)
        tr = r.get("trace") or {}
        row["model_items_rejected"] = len(tr.get("dropped") or [])
        row["model_items_accepted"] = len([s for s in stops if s.get("text_source") in ("ai", "calc")])
        row["error"] = (r.get("error") or {}).get("code")
        row["repair_attempts"] = tr.get("repair_attempts", 0)
        row["removed_claims"] = sum(len(w.get("claims", [])) for s in stops for w in s.get("warnings", []) if w["code"] == "ungrounded")
        row["wrong_language"] = sum(1 for s in stops for w in s.get("warnings", []) if w["code"] == "wrong_language")
        row["timings_ms"] = tr.get("timings_ms")
        row["retrieval_mode"] = tr.get("retrieval_mode")
        # --- name consistency: every stop carries sourced names for all three languages
        row["samples"] = [{"names": {l: f"{d['text']} [{d['kind']}]" + (f" ≈{d['translation']}" if d.get("translation") else "")
                                     for l, d in (s["poi"].get("display_names") or {}).items()},
                           "category": s["poi"]["category"], "text_source": s.get("text_source"),
                           "why": s.get("why"), "activity": s.get("activity"),
                           "warnings": [w["code"] + (":" + ",".join(w.get("claims", [])) if w.get("claims") else "") for w in s.get("warnings", [])]}
                          for s in stops]
        row["names_all_langs"] = all(set((s["poi"].get("display_names") or {})) == {"kk", "ru", "en"} for s in stops)
        # --- follow-up actions
        if plan and q.get("action") == "replace_first":
            others = [s["id"] for s in stops[1:]]
            st2, r2 = server.replace({**b, "plan_stops": [{"id": s["id"], "visit_minutes": s["visit_minutes"]} for s in stops],
                                      "target": stops[0]["id"], "reason": "replace"}, llm_call=model)
            ok = r2.get("replace", {}).get("ok")
            row["replace"] = {"ok": ok, "others_kept": (all(o in [s["id"] for s in r2["plan"]["stops"]] for o in others) if ok else None),
                              "within_budget": (r2["plan"]["total_min"] <= r2["plan"]["budget_min"]) if ok else None}
        if plan and q.get("action") == "walk_replan" and len(stops) >= 2:
            first = stops[0]["id"]
            b2 = {**b, "text": "", "start": {"type": "landmark", "id": first}, "return_to": start,
                  "plan_stops": [{"id": s["id"], "visit_minutes": s["visit_minutes"]} for s in stops[1:]],
                  "budget": max(5, plan["budget_min"] - stops[0]["leave_offset_min"])}
            st2, r2 = server.replan(b2)
            p2 = r2.get("plan")
            row["walk_replan"] = {"ok": bool(p2), "returns_to_original": bool(p2) and p2["legs"][-1]["to"] == "return",
                                  "within_remaining_time": bool(p2) and p2["total_min"] <= b2["budget"]}
        if plan and q.get("action") == "styles":
            sty = [x for x in (r.get("styles") or []) if x["key"] != "current"]   # alternatives only
            need = e.get("styles_min", 1)
            row["styles"] = {"alternatives": len(sty), "expected_at_least": need, "status": r.get("styles_status"),
                             "all_within_budget": all(x["total_min"] <= plan["budget_min"] for x in sty),
                             "all_distinct": len({tuple(x["stop_ids"]) for x in sty} | {tuple(s["id"] for s in stops)}) == len(sty) + 1,
                             "ok": len(sty) >= need}
        rows.append(row)
    return rows


def summarize(rows, live, model_calls):
    def rate(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return {"value": round(sum(1 for v in vals if v) / len(vals), 3) if vals else None, "n": len(vals)}
    out = {
        "queries": len(rows),
        "hit_at_5_category": rate("hit5_category"),
        "hit_at_5_named_place": rate("hit5_named"),
        "named_place_found_in_dataset": rate("named_in_dataset"),
        "named_place_unreachable_and_explained": rate("named_unreachable_explained"),
        "hit_at_5_poi_labels": rate("hit5_poi"),
        "clarification_correct": rate("clarify_ok"),
        "unknown_attributes_reported": rate("unknown_reported"),
        "plans_with_hard_constraint_violations": {"value": sum(1 for r in rows if r["violations"]), "n": len(rows)},
        "empty_no_feasible_place_with_suggestions": {
            "value": sum(1 for r in rows if r.get("empty_kind") == "no_feasible_place" and r.get("suggestions")),
            "n": sum(1 for r in rows if r.get("empty_kind") == "no_feasible_place")},
        "empty_because_model_failed": {"value": sum(1 for r in rows if r.get("empty_kind") == "model_failure"),
                                       "codes": sorted({r["error"] or "model_empty" for r in rows if r.get("empty_kind") == "model_failure"}),
                                       "queries": [r["id"] for r in rows if r.get("empty_kind") == "model_failure"]},
        "hit5_not_applicable_hard_filter": [r["id"] for r in rows if r.get("hit5_na_reason")],
        "starts": {"named_dataset_place": sum(1 for r in rows if r["start_kind"] == "named"),
                   "simulated_coordinates": sum(1 for r in rows if r["start_kind"] == "simulated")},
        "notices_ok": rate("notice_ok"),
        "names_in_all_languages": rate("names_all_langs"),
        "replacement_kept_others": [r["replace"] for r in rows if r.get("replace")],
        "walk_replan": [r["walk_replan"] for r in rows if r.get("walk_replan")],
        "styles": [r["styles"] for r in rows if r.get("styles")],
    }
    if live:
        acc = sum(r["model_items_accepted"] for r in rows)
        rej = sum(r["model_items_rejected"] for r in rows)
        out["model"] = {
            "valid_source_id_rate": {"value": round(acc / (acc + rej), 3) if acc + rej else None, "n_items": acc + rej},
            "malformed_after_repair": {"value": sum(1 for r in rows if r["error"] == "bad_json"), "n": len(rows)},
            "repair_attempts": sum(r["repair_attempts"] for r in rows),
            "removed_unsupported_claims": sum(r["removed_claims"] for r in rows),
            "wrong_language_warnings": sum(r["wrong_language"] for r in rows),
            "other_errors": sorted({r["error"] for r in rows if r["error"] and r["error"] != "bad_json"}),
            "output_tokens_max": max([r.get("model_tokens", {}).get("output") or 0 for r in rows] or [0]),
            "hit_output_cap": [r["id"] for r in rows if (r.get("model_tokens") or {}).get("done_reason") == "length"],
            "latency_s": {"first_call_incl_loading": round(model_calls[0], 2) if model_calls else None,
                          "later_calls_median": round(sorted(model_calls[1:])[len(model_calls[1:]) // 2], 2) if len(model_calls) > 1 else None,
                          "calls": len(model_calls)},
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=config.DATA_PATH)
    ap.add_argument("--live", action="store_true", help="call the configured model (Ollama/Gemini)")
    ap.add_argument("--mode", choices=["lexical", "hybrid", "both"], default="lexical")
    ap.add_argument("--now", default=None, help="Astana time YYYY-MM-DDTHH:MM (default: next Wednesday 14:30)")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    config.DATA_PATH = a.data
    config.WEATHER_ENABLED = False
    ds = load_dataset(a.data)
    if a.now:
        now = datetime.strptime(a.now, "%Y-%m-%dT%H:%M").replace(tzinfo=config.ASTANA_TZ)
    else:
        today = datetime.now(config.ASTANA_TZ)
        now = (today + timedelta(days=(2 - today.weekday()) % 7 or 7)).replace(hour=14, minute=30, second=0, microsecond=0)
    queries = json.loads((ROOT / "eval" / "queries.json").read_text(encoding="utf-8"))["queries"]
    labels: dict = {}
    lf = ROOT / "eval" / "labels.csv"
    if lf.exists():
        for row in csv.DictReader(lf.open(encoding="utf-8")):
            labels.setdefault(row["query_id"], {})[row["poi_id"]] = row.get("relevant", "").strip() in ("1", "y", "yes", "true")
    modes = ["lexical", "hybrid"] if a.mode == "both" else [a.mode]
    a.out.mkdir(parents=True, exist_ok=True)
    tag = "synthetic" if ds.is_synthetic else "real"
    for mode in modes:
        config.RETRIEVAL_MODE = mode
        model = Timed() if a.live else no_model
        rows = evaluate(ds, queries, model, now, labels)
        modes_used = sorted({r["retrieval_mode"] for r in rows if r.get("retrieval_mode")})
        summary = summarize(rows, a.live, model.calls if a.live else [])
        meta = {"dataset": str(a.data), "dataset_kind": tag, "places": len(ds.pois),
                "dataset_collected_at": ds.meta.get("collected_at"),
                "executed_at_astana_time": datetime.now(config.ASTANA_TZ).strftime("%Y-%m-%d %H:%M"),
                "simulated_planning_time": now.strftime("%Y-%m-%d %H:%M (%A)") + " — fixed scenario clock (use --now to change)",
                "retrieval_mode_requested": mode, "retrieval_mode_used": modes_used,
                "model": (llm.status().get("model") if a.live else "NO MODEL (deterministic selector)"),
                "labels": "category-level (eval/queries.json label_rules)" + (" + POI-level eval/labels.csv" if labels else "")}
        name = a.name or f"{tag}-{mode}-{'live' if a.live else 'nomodel'}"
        (a.out / f"{name}.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        with (a.out / f"{name}-to_label.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["query_id", "query", "rank", "poi_id", "name", "category", "relevant"])
            for q, r in zip(queries, rows):
                for i, p in enumerate(r["top5"], 1):
                    w.writerow([q["id"], q.get("text", ""), i, p["id"], p["name"], p["category"], ""])
        md = [f"# Evaluation: {name}", "", "Measured by eval/run_eval.py. Nothing here is estimated.", "",
              *[f"* {k}: {v}" for k, v in meta.items()], "", "## Summary", "", "```json",
              json.dumps(summary, ensure_ascii=False, indent=1), "```", "", "## Per query", "",
              "| id | lang | start used | top-5 categories | plan | violations | notes |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            notes = []
            for k in ("clarify", "clarify_ok", "named_excluded", "hit5_category", "hit5_na_reason", "hit5_named",
                      "empty_kind", "error", "model_tokens", "notice_ok", "unknown_reported", "empty", "suggestions", "replace", "walk_replan", "styles"):
                if r.get(k) not in (None, False, [], ""):
                    notes.append(f"{k}={r[k]}")
                elif r.get(k) is False:
                    notes.append(f"{k}=False")
            md.append(f"| {r['id']} | {r['lang']} | {r['start_used']} | {', '.join(p['category'] for p in r['top5'])} | "
                      f"{', '.join(p['category'] for p in r['plan'])} | {', '.join(r['violations']) or '—'} | {'; '.join(notes)} |")
        md += ["", "## Samples for human review (names in 3 languages with their source kind, and the AI text)", "",
               "Kinds: osm = OSM name:xx tag; original = original name shown unchanged; osm_latin = Latin name from OSM;",
               "wikidata = checked Wikidata label; override = reviewed. ≈ = labelled descriptive translation.", ""]
        for r in rows:
            for smp in r.get("samples", [])[:3]:
                md.append(f"* **{r['id']}** ({smp['category']}, text: {smp['text_source']}): kk «{smp['names'].get('kk')}» · "
                          f"ru «{smp['names'].get('ru')}» · en «{smp['names'].get('en')}»"
                          + (f"<br>why: {smp['why']}" if smp.get("why") else "")
                          + (f"<br>activity: {smp['activity']}" if smp.get("activity") else "")
                          + (f"<br>warnings: {', '.join(smp['warnings'])}" if smp.get("warnings") else ""))
        (a.out / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"[{name}] {json.dumps(summary, ensure_ascii=False)[:900]}")
        print(f"Written: {a.out / (name + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
