"""Check that the configured LLM answers, then run one full RAG request on the real dataset.

Usage (PowerShell):
    .venv\\Scripts\\python scripts\\check_llm.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walks import config, llm  # noqa: E402
from walks.data import DatasetError, load_dataset, start_landmarks  # noqa: E402
from walks.pipeline import run  # noqa: E402
from walks.retrieval import Request  # noqa: E402


def main() -> int:
    print(f"Provider: {llm.provider_name()}")
    if llm.provider_name() == "ollama":
        ok, msg = llm.check_ollama()
        print(msg)
        if not ok:
            return 1
    print("\n1) Tiny JSON request ...")
    try:
        reply = llm.generate('Reply with JSON only: {"ok": true}', "Are you working?")
    except llm.LLMError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"   model={reply.model}  time={reply.seconds:.1f}s  text={reply.text[:120]!r}")

    print("\n2) Full RAG request on the collected dataset ...")
    try:
        ds = load_dataset(config.DATA_PATH)
    except DatasetError as exc:
        print(f"SKIPPED: {exc}")
        return 0
    from walks.retrieval import retrieve
    text = "I have 45 minutes, want a walk and a coffee"
    req = start = None
    for cand in (start_landmarks(ds) or ds.pois[:1]):
        r0 = Request(text=text, lat=cand["lat"], lon=cand["lon"], budget_min=45, exclude_ids=(cand["id"],))
        if retrieve(ds, r0).candidates:
            req, start = r0, cand
            break
    if req is None:
        print("   No landmark has places within 45 minutes; nothing to send to the model.")
        return 1
    print(f"   Simulated start: {start['name']} ({start['id']})")
    res = run(ds, req, start_name=start["name"])
    if res.error:
        print(f"FAILED: {res.error}")
        return 1
    print(f"   Retrieved {len(res.retrieval.candidates)} candidates; model took {res.llm.seconds:.1f}s")
    for r in res.recommendations:
        print(f"   - {r.poi['name']} [{r.poi['id']}] {int(r.distance_m)} m straight-line, visit ~{r.visit_minutes} min")
        print(f"     why: {r.why}\n     do:  {r.activity}")
        for w in r.warnings:
            print(f"     WARNING: {w}")
    if res.dropped:
        print("   Dropped:", json.dumps(res.dropped, ensure_ascii=False))
    print(f"   note: {res.note}")
    ids_ok = all(r.poi["id"] in ds.by_id for r in res.recommendations)
    print(f"\nAll recommended IDs exist in dataset: {ids_ok}")
    return 0 if ids_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
