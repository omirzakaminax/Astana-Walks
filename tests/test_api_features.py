"""API tests for the eight features through server.py (fixed clock, FAKE model, SYNTHETIC places)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from walks import config  # noqa: E402
from tests.test_planning import DS, explain_all, fake_llm  # noqa: E402

TZ = config.ASTANA_TZ


class ApiFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "pois.json"
        path.write_text(json.dumps({"meta": {"is_synthetic": True, "collected_at": "2026-10-19T00:00:00+00:00"},
                                    "pois": DS.pois}, ensure_ascii=False), encoding="utf-8")
        cls.old_path, cls.old_weather, cls.old_clock = config.DATA_PATH, config.WEATHER_ENABLED, server.CLOCK
        config.DATA_PATH = path
        config.WEATHER_ENABLED = False
        server.CLOCK = lambda: datetime(2026, 10, 19, 14, 30, tzinfo=TZ)

    @classmethod
    def tearDownClass(cls):
        config.DATA_PATH, config.WEATHER_ENABLED, server.CLOCK = cls.old_path, cls.old_weather, cls.old_clock
        cls.tmp.cleanup()

    def body(self, **kw):
        b = {"text": "coffee and a walk", "lang": "en", "start": {"type": "coords", "lat": 51.089, "lon": 71.416},
             "budget": 120, "back": True, "interests": [], "weather": False}
        b.update(kw)
        return b

    # ---------- canonical plan
    def test_plan_is_canonical_in_response(self):
        st, r = server.recommend(self.body(), llm_call=fake_llm(["P1", "P2", "P3"]))
        self.assertEqual(st, 200)
        plan = r["plan"]
        self.assertEqual([s["id"] for s in plan["stops"]], [x["id"] for x in r["recommendations"]])
        self.assertEqual(plan["total_min"], sum(l["walk_min"] for l in plan["legs"]) + sum(s["visit_minutes"] for s in plan["stops"]))
        self.assertTrue(plan["fits"])
        self.assertEqual(plan["legs"][-1]["to"], "start")
        self.assertEqual(r["constraints"]["now"], "2026-10-19T14:30")

    # ---------- feature 1: deadline
    def test_deadline_caps_text_duration(self):
        st, r = server.recommend(self.body(text="I have two hours: 2 hours for coffee",
                                           deadline={"enabled": True, "at": "2026-10-19T15:30", "buffer_min": 10}),
                                 llm_call=fake_llm(["P1"]))
        self.assertEqual(st, 200)
        self.assertEqual(r["constraints"]["budget_min"], 50)
        self.assertEqual(r["constraints"]["budget_source"], "deadline")
        self.assertLessEqual(r["plan"]["total_min"], 50)
        self.assertTrue(r["start"]["back"])

    def test_deadline_errors(self):
        cases = [({"at": "2026-10-19T14:00"}, "deadline_past"), ({"at": "2026-10-19T14:35", "buffer_min": 10}, "deadline_buffer"),
                 ({"at": "garbage"}, "deadline_invalid"), ({"at": "2026-10-22T10:00"}, "deadline_too_far"),
                 ({"at": "2026-10-19T15:30", "buffer_min": 120}, "bad_buffer")]
        for dl, code in cases:
            st, r = server.recommend(self.body(deadline={"enabled": True, **dl}), llm_call=fake_llm(["P1"]))
            self.assertEqual((st, r["error"]["code"]), (400, code), dl)
        st, r = server.recommend(self.body(deadline={"enabled": True, "at": "2026-10-19T14:35", "buffer_min": 10}))
        self.assertEqual(r["error"]["params"], {"left": 5, "buffer": 10})

    # ---------- feature 7: pace, and no leakage between concurrent requests
    def test_pace_is_request_scoped(self):
        out = {}

        def go(name, pace):
            out[name] = server.recommend(self.body(text="walk park", pace=pace, budget=40), llm_call=fake_llm(["P1", "P2", "P3"]))
        ts = [threading.Thread(target=go, args=("slow", "leisurely")), threading.Thread(target=go, args=("fast", "brisk"))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out["slow"][1]["constraints"]["speed_m_per_min"], 45.0)
        self.assertEqual(out["fast"][1]["constraints"]["speed_m_per_min"], 95.0)
        slow_ids = {c["poi"]["id"] for c in out["slow"][1]["trace"]["candidates"]}
        fast_ids = {c["poi"]["id"] for c in out["fast"][1]["trace"]["candidates"]}
        self.assertTrue(slow_ids < fast_ids or slow_ids != fast_ids)

    # ---------- feature 3: outdoor cap
    def test_outdoor_cap_is_hard_and_not_relaxed(self):
        st, r = server.recommend(self.body(text="walk park", outdoor={"max_min": 3}), llm_call=fake_llm(["P1"]))
        self.assertEqual(st, 200)
        self.assertIsNone(r["plan"])
        self.assertIn(r["note_code"], ("no_plan_outdoor", "no_candidates"))
        st, r = server.recommend(self.body(text="coffee", outdoor={"max_min": 20}), llm_call=fake_llm(["P1"]))
        self.assertLessEqual(r["plan"]["outdoor_min"], 20)
        self.assertEqual(r["constraints"]["outdoor"]["max_min"], 20)

    # ---------- feature 6: group
    def test_group_min_time_slowest_pace_and_coverage(self):
        g = {"participants": [{"interests": ["coffee"], "minutes": 90, "pace": "brisk"},
                              {"interests": ["walk"], "minutes": 45, "pace": "leisurely"}]}
        st, r = server.recommend(self.body(text="", group=g), llm_call=fake_llm(["P1"]))
        self.assertEqual(st, 200)
        c = r["constraints"]
        self.assertEqual((c["budget_min"], c["pace"]), (45, "leisurely"))
        self.assertEqual(len(r["coverage"]), 2)
        self.assertLessEqual(r["plan"]["total_min"], 45)
        st, solo = server.recommend(self.body(text="coffee"), llm_call=fake_llm(["P1"]))
        self.assertEqual(solo["constraints"]["group"], [])
        self.assertEqual(solo["coverage"], [])
        for bad in ({"participants": [g["participants"][0]]}, {"participants": g["participants"] * 3}, {"participants": "x"}):
            st, r = server.recommend(self.body(group=bad))
            self.assertEqual(st, 400)

    # ---------- feature 2: replace / visited / closed / remove
    def test_replace_flow(self):
        st, r = server.recommend(self.body(), llm_call=fake_llm(["P1", "P2", "P3"]))
        stops = [{"id": s["id"], "visit_minutes": s["visit_minutes"]} for s in r["plan"]["stops"]]
        target = stops[0]["id"]
        st, rep = server.replace(self.body(plan_stops=stops, target=target, reason="closed",
                                           exclude={"unavailable": [target]}), llm_call=explain_all())
        self.assertEqual(st, 200)
        self.assertTrue(rep["replace"]["ok"])
        new_ids = [s["id"] for s in rep["plan"]["stops"]]
        self.assertNotIn(target, new_ids)
        for s in stops[1:]:
            self.assertIn(s["id"], new_ids)
        kept = [s for s in rep["plan"]["stops"] if s["id"] != rep["replace"]["new_id"]]
        self.assertTrue(all(s["text_source"] == "keep" for s in kept))
        new = next(s for s in rep["plan"]["stops"] if s["id"] == rep["replace"]["new_id"])
        self.assertIn(new["text_source"], ("ai", "calc"))
        # remove a stop -> replan
        st, rp = server.replan(self.body(plan_stops=[s for s in stops if s["id"] != target]))
        self.assertEqual([s["id"] for s in rp["plan"]["stops"]].__len__(), len(stops) - 1)

    def test_replace_invalid_inputs(self):
        good = [{"id": "syn:1", "visit_minutes": 20}]
        bad_bodies = [dict(plan_stops=good, target="syn:3"), dict(plan_stops=good, target="syn:1", reason="angry"),
                      dict(plan_stops=[{"id": "nope", "visit_minutes": 20}], target="nope"),
                      dict(plan_stops=good * 2, target="syn:1"), dict(plan_stops=[], target="syn:1"),
                      dict(plan_stops=[{"id": "syn:1", "visit_minutes": "x"}], target="syn:1")]
        for b in bad_bodies:
            st, r = server.replace(self.body(**b), llm_call=explain_all())
            self.assertEqual((st, r["error"]["code"]), (400, "bad_plan"), b)

    # ---------- feature 4: surprise
    def test_surprise_api(self):
        st, a = server.recommend(self.body(text="", mode="surprise", surprise={"seed": 7, "avoid": []}), llm_call=explain_all())
        self.assertEqual(st, 200)
        ids = [s["id"] for s in a["plan"]["stops"]]
        self.assertEqual(a["mode"], "surprise")
        st, b = server.recommend(self.body(text="", mode="surprise", surprise={"seed": 7, "avoid": [ids]}), llm_call=explain_all())
        self.assertNotEqual(set(ids), {s["id"] for s in b["plan"]["stops"]})
        st, v = server.recommend(self.body(text="", mode="surprise", surprise={"seed": 7, "avoid": []},
                                           exclude={"visited": ids}), llm_call=explain_all())
        self.assertFalse(set(ids) & {s["id"] for s in v["plan"]["stops"]})
        st, bad = server.recommend(self.body(mode="surprise", surprise={"seed": "x"}))
        self.assertEqual(st, 400)
        st, bad = server.recommend(self.body(mode="surprise", surprise={"avoid": "x"}))
        self.assertEqual(st, 400)

    # ---------- general validation
    def test_invalid_inputs_are_structured(self):
        for b, code in ((dict(pace="sprint"), "bad_pace"), (dict(budget=-5), "bad_budget"),
                        (dict(interests=["<script>"]), "bad_interests"), (dict(outdoor={"max_min": 999}), "bad_outdoor"),
                        (dict(exclude={"visited": [1, 2]}), "bad_exclusions"), (dict(mode="hack"), "bad_request")):
            st, r = server.recommend(self.body(**b), llm_call=fake_llm(["P1"]))
            self.assertEqual((st, r["error"]["code"]), (400, code), b)

    def test_old_request_format_still_works(self):
        st, r = server.recommend({"text": "coffee", "lang": "ru", "start": {"type": "coords", "lat": 51.089, "lon": 71.416}},
                                 llm_call=fake_llm(["P1"]))
        self.assertEqual(st, 200)
        self.assertEqual(r["constraints"]["pace"], "normal")
        self.assertTrue(r["plan"])


if __name__ == "__main__":
    unittest.main()
