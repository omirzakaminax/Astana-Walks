"""OPTIONAL semantic retrieval (RETRIEVAL_MODE=hybrid): a local multilingual embedding model,
fused with the lexical ranking by reciprocal-rank fusion (RRF).

* Model: intfloat/multilingual-e5-small by default (SEMANTIC_MODEL). Per its model card, queries are
  prefixed with "query: " and documents with "passage: ", and embeddings are L2-normalised.
* Runs on CPU, loaded once per process. Document embeddings are cached on disk
  (data/cache/emb-<hash>.npz), keyed by the dataset content AND the model name.
* Hard constraints are applied BEFORE this step (only the already-eligible pool is re-ranked), and
  the itinerary is checked again afterwards; similarity never makes a closed/too-far place eligible.
* Not installed / cannot load -> SemanticUnavailable; retrieval falls back to lexical and the
  response says which mode actually ran. Kazakh quality is NOT assumed: see docs/EVALUATION.md.

Install (separately from the base app): pip install -r requirements-semantic.txt
"""
from __future__ import annotations

import hashlib
import json
import threading

from . import config

RRF_K = 60
_lock = threading.Lock()
_state: dict = {"model": None, "encoder": None, "docs_key": None, "doc_vecs": None, "doc_ids": None}


class SemanticUnavailable(RuntimeError):
    pass


def set_encoder(fn) -> None:
    """Tests: inject fn(list[str]) -> list[list[float]] (already normalised)."""
    with _lock:
        _state.update(encoder=fn, docs_key=None, doc_vecs=None, doc_ids=None)


def _load_encoder():
    if _state["encoder"] is not None:
        return _state["encoder"]
    try:
        from sentence_transformers import SentenceTransformer  # optional dependency
    except Exception as exc:  # ImportError or a broken torch install
        raise SemanticUnavailable(f"sentence-transformers not installed ({type(exc).__name__})") from None
    try:
        model = SentenceTransformer(config.SEMANTIC_MODEL, device="cpu")
    except Exception as exc:
        raise SemanticUnavailable(f"model {config.SEMANTIC_MODEL} could not be loaded ({type(exc).__name__})") from None

    def enc(texts):
        return model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()

    _state["encoder"] = enc
    return enc


def passage_text(poi: dict) -> str:
    from .retrieval import poi_document
    return "passage: " + poi_document(poi)[:600]


def _docs_key(ds) -> str:
    h = hashlib.sha1(config.SEMANTIC_MODEL.encode())
    for p in ds.pois:
        h.update(json.dumps([p["id"], passage_text(p)], ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def _doc_vectors(ds, enc):
    key = _docs_key(ds)
    if _state["docs_key"] == key:
        return _state["doc_ids"], _state["doc_vecs"]
    cache = config.CACHE_DIR / f"emb-{key}.json"
    ids, vecs = None, None
    if cache.exists() and _state["encoder"] is not None and not getattr(enc, "is_fake", False):
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
            ids, vecs = raw["ids"], raw["vecs"]
        except (OSError, ValueError, KeyError):
            ids = None
    if ids is None:
        ids = [p["id"] for p in ds.pois]
        vecs = enc([passage_text(p) for p in ds.pois])
        if not getattr(enc, "is_fake", False):
            try:
                config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"model": config.SEMANTIC_MODEL, "ids": ids, "vecs": vecs}), encoding="utf-8")
            except OSError:
                pass  # caching is an optimisation only
    _state.update(docs_key=key, doc_ids=ids, doc_vecs=vecs)
    return ids, vecs


def fuse(ds, query: str, pool: list) -> list:
    """Re-rank the eligible pool: RRF of (lexical rank, semantic rank). Returns a new list."""
    with _lock:
        enc = _load_encoder()
        ids, vecs = _doc_vectors(ds, enc)
        qv = enc(["query: " + query])[0]
    pos = {pid: i for i, pid in enumerate(ids)}
    sims = {}
    for c in pool:
        i = pos.get(c.poi["id"])
        sims[c.poi["id"]] = sum(a * b for a, b in zip(qv, vecs[i])) if i is not None else -1.0
    lex_rank = {c.poi["id"]: r for r, c in enumerate(pool, start=1)}
    sem_order = sorted(pool, key=lambda c: -sims[c.poi["id"]])
    sem_rank = {c.poi["id"]: r for r, c in enumerate(sem_order, start=1)}
    for c in pool:
        rrf = 1 / (RRF_K + lex_rank[c.poi["id"]]) + 1 / (RRF_K + sem_rank[c.poi["id"]])
        c.parts.update(semantic=round(sims[c.poi["id"]], 3), rrf=round(rrf, 5))
    return sorted(pool, key=lambda c: (-c.parts["rrf"], c.distance_m))


def status() -> dict:
    if config.RETRIEVAL_MODE != "hybrid":
        return {"mode": "lexical", "detail": "RETRIEVAL_MODE=lexical"}
    try:
        _load_encoder()
        return {"mode": "hybrid", "detail": config.SEMANTIC_MODEL}
    except SemanticUnavailable as exc:
        return {"mode": "lexical", "detail": f"hybrid requested but unavailable: {exc}"}
