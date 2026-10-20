"""Check that everything needed for the demo works on this laptop, and measure what can be measured.

Usage (PowerShell, from the project folder):
    .venv\\Scripts\\python scripts\\doctor.py            # Python, packages, dataset, names, model status
    .venv\\Scripts\\python scripts\\doctor.py --infer    # + two real model calls (warm-up vs warm latency)
Prints PASS / WARN / FAIL lines. Nothing is changed; no data leaves the laptop except the optional
model call to your local Ollama (or Gemini, if you configured it).
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walks import config  # noqa: E402

results: list[tuple[str, str, str]] = []


def say(level: str, what: str, detail: str = "") -> None:
    results.append((level, what, detail))
    print(f"{level:4s} {what}" + (f" — {detail}" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--infer", action="store_true", help="make two real model calls and time them")
    a = ap.parse_args()

    v = sys.version_info
    say("PASS" if (3, 10) <= v[:2] <= (3, 13) else "WARN", f"Python {platform.python_version()}",
        "" if (3, 10) <= v[:2] <= (3, 13) else "tested with 3.10–3.13")
    try:
        import requests  # noqa: F401
        say("PASS", "package: requests")
    except ImportError:
        say("FAIL", "package: requests", "run: .venv\\Scripts\\pip install -r requirements.txt")
        return 1

    from walks import llm, semantic
    from walks.data import DatasetError, load_dataset
    from walks.report import data_quality, naming_audit

    try:
        t0 = time.perf_counter()
        ds = load_dataset(config.DATA_PATH)
        load_ms = (time.perf_counter() - t0) * 1000
        dq, na = data_quality(ds), naming_audit(ds)
        say("FAIL" if ds.is_synthetic else "PASS", f"dataset: {len(ds.pois)} places from {config.DATA_PATH}",
            "SYNTHETIC test data — collect real data before the demo" if ds.is_synthetic else
            f"collected {dq['collected_at_latest']}, loaded in {load_ms:.0f} ms, schema v{dq['schema_version']}")
        if ds.skip_reasons:
            say("WARN", "records skipped on load", json.dumps(ds.skip_reasons))
        en = na["display_name_source_by_language"]["en"]
        say("PASS", "English names by source", json.dumps(en, ensure_ascii=False))
        if na["records_with_legacy_unverified_names"]:
            say("WARN", f"{na['records_with_legacy_unverified_names']} records had unverified legacy names",
                "kept only as search aliases; re-run collect_osm.py --all to refresh provenance")
        media = dq["media"]
        say("PASS" if media["with_photo"] else "WARN", f"media: {media['with_photo']} photos, {media['with_description']} descriptions",
            "" if media["with_photo"] else "run scripts\\enrich_wiki.py")
        if not media.get("wikidata_identity"):
            say("WARN", "Wikidata identity checks not stored yet", "re-run scripts\\enrich_wiki.py (labels are not shown as names until checked)")
        from walks.search import index_for
        t0 = time.perf_counter()
        idx = index_for(ds)
        hits = idx.search("baiterek", 3)
        say("PASS", f"search index built in {(time.perf_counter() - t0) * 1000:.0f} ms",
            f"'baiterek' -> {[h[0]['name'] for h in hits] or 'no match in this dataset'}")
    except DatasetError as exc:
        ds = None
        say("FAIL", "dataset", str(exc))

    st = llm.status()
    say("PASS" if st["ok"] else "FAIL", f"model: {st['provider']} {st.get('model')}", st["detail"])
    sem = semantic.status()
    say("PASS" if config.RETRIEVAL_MODE != "hybrid" or sem["mode"] == "hybrid" else "WARN",
        f"retrieval mode: {sem['mode']}", sem["detail"])

    if a.infer and st["ok"] and ds is not None:
        from walks.data import start_landmarks
        from walks.pipeline import run
        from walks.retrieval import Request
        start = (start_landmarks(ds) or ds.pois)[0]
        times = []
        for i in range(2):
            req = Request(text="45 minutes: a coffee and a short walk", lat=start["lat"], lon=start["lon"], budget_min=45,
                          answer_lang="en", exclude_ids=(start["id"],))
            t0 = time.perf_counter()
            res = run(ds, req, start_name=start["name"])
            times.append(time.perf_counter() - t0)
            if res.error:
                say("FAIL", f"model inference #{i + 1}", res.error)
                break
            tm = res.timings_ms
            say("PASS", f"model inference #{i + 1}: {times[-1]:.1f} s total",
                f"retrieval {tm.get('retrieval')} ms, planning {tm.get('planning')} ms, model {tm.get('generation')} ms, "
                f"{len(res.recommendations)} stops, repair attempts {res.repair_attempts}")
        if len(times) == 2:
            say("PASS", "warm-up vs warm", f"first {times[0]:.1f} s (includes model loading), second {times[1]:.1f} s")
    elif a.infer:
        say("WARN", "model inference skipped", "model or dataset not ready")

    fails = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(fails)} OK/WARN, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
