"""Kazakh language support, weather logic and the local web server / API.

All data is the SYNTHETIC fixture; the model is a FAKE function; weather is mocked.
Nothing here contacts OpenStreetMap, Open-Meteo or a real model.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["WALKS_DATA_PATH"] = str(ROOT / "tests" / "fixtures" / "synthetic_pois.json")

from walks import config, weather  # noqa: E402

config.DATA_PATH = Path(os.environ["WALKS_DATA_PATH"])
config.WEATHER_ENABLED = False

import server  # noqa: E402
from walks.categories import CATEGORIES, LANGS, label  # noqa: E402
from walks.data import load_dataset  # noqa: E402
from walks.llm import LLMError, LLMReply  # noqa: E402
from walks.pipeline import run, to_dict, ungrounded_claims  # noqa: E402
from walks.retrieval import Request, retrieve  # noqa: E402
from walks.text import INTENT_LABELS, UNSUPPORTED_LABELS, detect_intents, detect_language, detect_unsupported, parse_minutes  # noqa: E402

START = (51.0890, 71.4160)
MONDAY_14 = datetime(2026, 10, 19, 14, 0, tzinfo=config.ASTANA_TZ)


def fake_llm(payload):
    def call(system, user):
        call.system, call.user = system, user
        return LLMReply(json.dumps(payload), "fake", "fake-model", 0.01)
    return call


class KazakhTests(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(detect_language("Баламен бірге бір сағатымыз бар"), "kk")
        self.assertEqual(detect_language("Я с ребёнком"), "ru")
        self.assertEqual(detect_language("with a child"), "en")

    def test_kazakh_intents_and_time(self):
        self.assertIn("kids", detect_intents("Баламен бірге бір сағатымыз бар"))
        self.assertEqual(parse_minutes("Баламен бірге бір сағатымыз бар"), 60)
        self.assertIn("walk", detect_intents("Мен EXPO жанындамын, 45 минутым бар. Қайда серуендеуге болады?"))
        self.assertEqual(parse_minutes("45 минутым бар"), 45)
        self.assertEqual(parse_minutes("2 сағатым бар"), 120)
        self.assertEqual(parse_minutes("жарты сағат"), 30)
        self.assertIn("sights", detect_intents("Мен туристпін: жақын жерде не көруге болады?"))
        self.assertEqual(set(detect_unsupported("кофе ішетін тыныш орын, розеткасы болса")), {"quiet", "sockets"})

    def test_labels_complete_in_three_languages(self):
        for key in CATEGORIES:
            for lang in LANGS:
                self.assertTrue(label(key, lang), (key, lang))
        for table in (INTENT_LABELS, UNSUPPORTED_LABELS):
            for key, labels in table.items():
                self.assertEqual(set(labels), set(LANGS), key)

    def test_answer_language_is_passed_to_model(self):
        llm = fake_llm({"recommendations": [{"id": "P1", "why": "ж", "activity": "а", "visit_minutes": 20}]})
        ds = load_dataset(config.DATA_PATH)
        run(ds, Request("coffee", *START, 60, now=MONDAY_14, answer_lang="kk"), llm_call=llm)
        self.assertIn("Kazakh", llm.system)
        self.assertIn("Answer language: Kazakh", llm.user)
        self.assertIn("Кафе", llm.user)  # category label in Kazakh in the evidence

    def test_kazakh_open_now_claim_flagged(self):
        self.assertEqual(ungrounded_claims("Қазір ашық, кофе ішіңіз.", {"name": "x"}, "not_listed"), ["open_now"])
        self.assertEqual(ungrounded_claims("Қазір ашық.", {"name": "x"}, "open"), [])


class WeatherTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(weather.classify(-18, -25, 0, 3), (True, ["cold"]))
        self.assertEqual(weather.classify(18, 18, 0, 3), (False, []))
        self.assertEqual(weather.classify(10, 10, 1.2, 14), (True, ["precipitation", "wind"]))

    def test_harsh_weather_boosts_indoor(self):
        ds = load_dataset(config.DATA_PATH)
        harsh = weather.Weather(-20, -27, 0, 5, 3, True, ["cold"])
        mild = weather.Weather(18, 18, 0, 2, 1, False, [])
        q = "I want a walk or a coffee"
        rr_h = retrieve(ds, Request(q, *START, 60, interests=["coffee"], now=MONDAY_14, weather=harsh))
        rr_m = retrieve(ds, Request(q, *START, 60, interests=["coffee"], now=MONDAY_14, weather=mild))
        self.assertTrue(rr_h.candidates[0].poi["category"] == "cafe")
        self.assertGreater(rr_h.candidates[0].parts["bonus"], 0)
        self.assertEqual(max(c.parts["bonus"] for c in rr_m.candidates), 0)

    def test_weather_failure_returns_none(self):
        weather._CACHE.clear()
        bad = mock.Mock()
        bad.get.side_effect = OSError("no network")
        self.assertIsNone(weather.current(51.09, 71.41, session=bad))

    def test_weather_parsing(self):
        weather._CACHE.clear()
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"current": {"temperature_2m": -12.4, "apparent_temperature": -19.0,
                                              "precipitation": 0.0, "weather_code": 3, "wind_speed_10m": 6.0,
                                              "time": "2026-10-19T14:00"}}
        sess = mock.Mock()
        sess.get.return_value = resp
        w = weather.current(51.09, 71.41, session=sess)
        self.assertTrue(w.harsh)
        self.assertIn("cold", w.reasons)
        self.assertIn("-12°C", w.summary_en())


class ApiTests(unittest.TestCase):
    """Real HTTP round-trips against server.py on a random local port, with a FAKE model."""

    @classmethod
    def setUpClass(cls):
        server.Handler.llm_call = staticmethod(fake_llm({"recommendations": [
            {"id": "P1", "why": "Близко и подходит по времени.", "activity": "Пройдитесь по аллее.", "visit_minutes": 20}],
            "note": ""}))
        cls.srv = server.make_server("127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        server.Handler.llm_call = None

    def get(self, path):
        try:
            with self.opener.open(self.base + path, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(self, body, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + "/api/recommend", data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_index_and_assets(self):
        st, h, body = self.get("/")
        self.assertEqual(st, 200)
        self.assertIn(b"Astana Walks", body)
        for asset in ("/assets/app.js", "/assets/i18n.js", "/assets/styles.css"):
            st, h, _ = self.get(asset)
            self.assertEqual(st, 200, asset)
        st, h, _ = self.get("/")
        self.assertEqual(h["Referrer-Policy"], "strict-origin-when-cross-origin")  # OSM tiles need a Referer
        st, _, _ = self.get("/assets/../server.py")
        self.assertEqual(st, 404)

    def test_meta(self):
        st, _, body = self.get("/api/meta")
        m = json.loads(body)
        self.assertEqual(st, 200)
        self.assertTrue(m["dataset"]["is_synthetic"])
        self.assertEqual(m["dataset"]["count"], 12)
        self.assertTrue(m["landmarks"])
        self.assertEqual(set(m["labels"]["categories"]["cafe"]), {"kk", "ru", "en"})

    def test_recommend_landmark(self):
        ds = load_dataset(config.DATA_PATH)
        lm = ds.by_id["fixture:5"]  # "Synthetic Near Park", close to the cafés
        st, r = self.post({"text": "кофе 45 минут", "lang": "ru", "start": {"type": "landmark", "id": lm["id"]},
                           "budget": 60, "back": True, "interests": [], "weather": False})
        self.assertEqual(st, 200)
        self.assertEqual(r["understood"]["budget_min"], 45)
        self.assertEqual(len(r["recommendations"]), 1)
        rec = r["recommendations"][0]
        self.assertIn(rec["poi"]["id"], ds.by_id)
        self.assertIn(rec["hours"]["key"], ("open", "open_24_7", "closed", "unknown", "not_listed"))
        self.assertTrue(r["start"]["back"])
        self.assertNotIn("fixture:5", [c["poi"]["id"] for c in r["trace"]["candidates"]])  # not the start itself
        self.assertTrue(r["trace"]["candidates"])

    def test_recommend_coords_and_errors(self):
        ok, r = self.post({"text": "coffee", "lang": "en", "start": {"type": "coords", "lat": 51.089, "lon": 71.416}})
        self.assertEqual(ok, 200)
        st, r = self.post({"text": "coffee", "lang": "en", "start": {"type": "coords", "lat": 43.2, "lon": 76.9}})
        self.assertEqual((st, r["error"]["code"]), (400, "outside_astana"))
        st, r = self.post({"text": "coffee", "lang": "en", "start": {"type": "coords", "lat": "abc", "lon": 71}})
        self.assertEqual((st, r["error"]["code"]), (400, "bad_coords"))
        st, r = self.post({"text": "  ", "lang": "kk", "start": {"type": "coords", "lat": 51.089, "lon": 71.416}})
        self.assertEqual((st, r["error"]["code"]), (400, "empty_request"))
        st, r = self.post({"text": "coffee", "start": {"type": "landmark", "id": "nope"}})
        self.assertEqual(st, 400)
        st, r = self.post(None, raw=b"not json")
        self.assertEqual((st, r["error"]["code"]), (400, "bad_request"))

    def test_llm_error_code_reaches_client(self):
        def boom(system, user):
            raise LLMError("Cannot reach Ollama", "ollama_unreachable", url="http://localhost:11434")
        st, r = server.recommend({"text": "coffee", "lang": "kk", "start": {"type": "coords", "lat": 51.089, "lon": 71.416}},
                                 llm_call=boom)
        self.assertEqual(st, 200)
        self.assertEqual(r["error"]["code"], "ollama_unreachable")
        self.assertEqual(r["error"]["params"]["url"], "http://localhost:11434")
        self.assertTrue(r["trace"]["candidates"])  # search results still available, labelled in the UI
        json.dumps(r, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
