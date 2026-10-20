"""Collector + HTTP tests. Uses SYNTHETIC OSM-like elements and a LOCAL MOCK Ollama server.
Nothing here contacts OpenStreetMap or a real model.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from walks import config, llm  # noqa: E402
from walks.osm_collect import CollectionError, build_query, collect, deduplicate, fetch_overpass, normalize  # noqa: E402

C = (51.0890, 71.4160)
ELEMENTS = [  # synthetic, OSM-shaped
    {"type": "node", "id": 1, "lat": 51.0900, "lon": 71.4170, "tags": {"amenity": "cafe", "name": "Test Cafe", "opening_hours": "Mo-Su 09:00-21:00", "cuisine": "coffee_shop"}},
    {"type": "way", "id": 2, "center": {"lat": 51.0901, "lon": 71.4171}, "tags": {"amenity": "cafe", "name": "Test cafe", "building": "yes"}},
    {"type": "node", "id": 3, "lat": 51.0880, "lon": 71.4150, "tags": {"leisure": "playground"}},
    {"type": "node", "id": 4, "lat": 51.0880, "lon": 71.4150, "tags": {"amenity": "bench"}},
    {"type": "node", "id": 5, "lat": 51.0870, "lon": 71.4140, "tags": {"amenity": "cafe"}},  # unnamed cafe -> dropped
    {"type": "node", "id": 6, "lat": 95.0, "lon": 71.4140, "tags": {"amenity": "cafe", "name": "Bad coords"}},
    {"type": "node", "id": 7, "lat": 51.2000, "lon": 71.4160, "tags": {"tourism": "museum", "name": "Too Far"}},
    {"type": "node", "id": 8, "lat": 51.0895, "lon": 71.4180, "tags": {"tourism": "museum", "name": "Test Museum", "description": "A test description."}},
]


class CollectorTests(unittest.TestCase):
    def test_query_contains_area_and_categories(self):
        q = build_query(*C, 2000)
        self.assertIn("around:2000,51.089000,71.416000", q)
        self.assertIn("out center tags", q)

    def test_normalize_and_dedupe(self):
        pois = deduplicate(normalize(ELEMENTS, C, 2500, "2026-10-19T00:00:00+00:00"))
        names = sorted(p["name"] for p in pois)
        self.assertEqual(names, ["Test Cafe", "Test Museum", "Детская площадка (без названия в OSM)"])
        cafe = next(p for p in pois if p["name"] == "Test Cafe")
        self.assertEqual(cafe["id"], "osm:node/1")
        self.assertEqual(cafe["source_url"], "https://www.openstreetmap.org/node/1")
        self.assertEqual(cafe["opening_hours"], "Mo-Su 09:00-21:00")
        self.assertEqual(cafe["description_source"], "summary_of_osm_tags")
        self.assertIn("Summary of OpenStreetMap tags", cafe["description"])
        museum = next(p for p in pois if p["name"] == "Test Museum")
        self.assertEqual(museum["description_source"], "osm_description_tag")
        pg = next(p for p in pois if p["name_is_generated"])
        self.assertIsNone(pg["opening_hours"])  # never invented

    def test_failed_collection_keeps_existing_file(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "pois.json"
            out.write_text('{"meta": {}, "pois": ["old"]}', encoding="utf-8")

            def failing_fetch(query):
                raise CollectionError("All Overpass endpoints failed: timeout")
            with self.assertRaises(CollectionError):
                collect(C, 2500, 150, out, fetch=failing_fetch, log=lambda *a: None)
            self.assertIn("old", out.read_text(encoding="utf-8"))

    def test_successful_collection_writes_file(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "pois.json"
            data = collect(C, 2500, 150, out, fetch=lambda q: {"elements": ELEMENTS}, log=lambda *a: None)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["meta"]["count"], data["meta"]["count"])
            self.assertFalse(saved["meta"]["is_synthetic"])
            self.assertTrue(all("_dist" not in p for p in saved["pois"]))

    def test_merge_adds_new_area_without_duplicates(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "pois.json"
            collect(C, 2500, 150, out, fetch=lambda q: {"elements": ELEMENTS}, log=lambda *a: None)
            first = json.loads(out.read_text(encoding="utf-8"))["meta"]["count"]
            extra = ELEMENTS[:1] + [{"type": "node", "id": 99, "lat": 51.0905, "lon": 71.4175,
                                     "tags": {"leisure": "park", "name": "Second Area Park"}}]
            data = collect(C, 2500, 150, out, fetch=lambda q: {"elements": extra}, log=lambda *a: None, merge=True)
            self.assertEqual(data["meta"]["count"], first + 1)          # cafe duplicate skipped, park added
            self.assertEqual(len(data["meta"]["areas"]), 2)
            self.assertEqual(data["meta"]["areas"][1]["added"], 1)

    def test_merge_refuses_synthetic_file(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "pois.json"
            out.write_text('{"meta": {"is_synthetic": true}, "pois": []}', encoding="utf-8")
            with self.assertRaises(CollectionError):
                collect(C, 2500, 150, out, fetch=lambda q: {"elements": ELEMENTS}, log=lambda *a: None, merge=True)

    def test_fetch_retries_then_fails_cleanly(self):
        session = mock.Mock(spec=requests.Session)
        session.headers = {}
        session.post.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(CollectionError) as ctx:
            fetch_overpass("q", endpoints=["https://a.invalid", "https://b.invalid"], session=session,
                           sleep=lambda s: None, log=lambda *a: None)
        self.assertEqual(session.post.call_count, 4)
        self.assertIn("Timeout", str(ctx.exception))
        self.assertIn("AstanaWalks", session.headers["User-Agent"])


class _MockOllama(BaseHTTPRequestHandler):
    last_body = None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockOllama.last_body = body
        if body["model"] == "missing-model":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"model not found"}')
            return
        reply = {"message": {"role": "assistant", "content": '{"recommendations": [], "note": "mock"}'}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class OllamaHttpTests(unittest.TestCase):
    """Real HTTP round-trip against a LOCAL MOCK server (not a real model)."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _MockOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_request_format_and_reply(self):
        with mock.patch.object(config, "OLLAMA_URL", self.url), mock.patch.object(config, "LLM_PROVIDER", "ollama"):
            reply = llm.generate("sys", "user")
        self.assertEqual(json.loads(reply.text)["note"], "mock")
        body = _MockOllama.last_body
        self.assertEqual(body["format"], "json")
        self.assertFalse(body["stream"])
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])

    def test_qwen3_disables_thinking(self):
        with mock.patch.object(config, "OLLAMA_URL", self.url), mock.patch.object(config, "OLLAMA_MODEL", "qwen3:4b"):
            llm.generate("sys", "user")
        self.assertIs(_MockOllama.last_body.get("think"), False)
        with mock.patch.object(config, "OLLAMA_URL", self.url), mock.patch.object(config, "OLLAMA_MODEL", "qwen2.5:1.5b"):
            llm.generate("sys", "user")
        self.assertNotIn("think", _MockOllama.last_body)
        for name in ("qwen3:4b-instruct", "qwen3-vl:4b-instruct"):
            self.assertFalse(llm.is_thinking_model(name), name)
        with mock.patch.object(config, "OLLAMA_URL", self.url), mock.patch.object(config, "OLLAMA_MODEL", "qwen3-vl:4b-instruct"):
            llm.generate("sys", "user")
        self.assertNotIn("think", _MockOllama.last_body)

    def test_missing_model_message(self):
        with mock.patch.object(config, "OLLAMA_URL", self.url), mock.patch.object(config, "OLLAMA_MODEL", "missing-model"):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.generate("s", "u")
        self.assertIn("ollama pull missing-model", str(ctx.exception))

    def test_ollama_down_message(self):
        with mock.patch.object(config, "OLLAMA_URL", "http://127.0.0.1:9"):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.generate("s", "u")
        self.assertIn("Cannot reach Ollama", str(ctx.exception))

    def test_gemini_without_key(self):
        with mock.patch.object(config, "LLM_PROVIDER", "gemini"), mock.patch.object(config, "GEMINI_API_KEY", ""):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.generate("s", "u")
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
