"""Core logic tests. ALL data here is SYNTHETIC fixture data (tests/fixtures), not collected data.

Run:  python -m pytest -q     (or: python -m unittest discover -s tests -v)
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from walks import config  # noqa: E402
from walks.data import DatasetError, load_dataset  # noqa: E402
from walks.geo import InvalidCoordinates, approx_walk_minutes, haversine_m, max_reachable_distance_m, validate_coords  # noqa: E402
from walks.hours import status_at  # noqa: E402
from walks.llm import LLMError, LLMReply  # noqa: E402
from walks.pipeline import run, ungrounded_claims  # noqa: E402
from walks.retrieval import EmptyRequest, Request, retrieve  # noqa: E402
from walks.text import detect_intents, detect_language, detect_unsupported, parse_minutes  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_pois.json"
START = (51.0890, 71.4160)
MONDAY_14 = datetime(2026, 10, 19, 14, 0, tzinfo=config.ASTANA_TZ)
TUESDAY_14 = datetime(2026, 10, 20, 14, 0, tzinfo=config.ASTANA_TZ)


def ds():
    return load_dataset(FIXTURE)


def fake_llm(payload):
    def call(system, user):
        call.system, call.user = system, user
        return LLMReply(json.dumps(payload) if not isinstance(payload, str) else payload, "fake", "fake-model", 0.01)
    return call


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # 0.01 degree latitude ~ 1112 m
        self.assertAlmostEqual(haversine_m(51.0, 71.4, 51.01, 71.4), 1112, delta=3)

    def test_invalid_coordinates(self):
        for bad in [("abc", 71.4), (None, 71.4), (95, 71.4), (51.0, 200), (43.2, 76.9)]:  # last = Almaty
            with self.assertRaises(InvalidCoordinates):
                validate_coords(*bad)
        self.assertEqual(validate_coords("51.09", "71.41"), (51.09, 71.41))

    def test_walk_time_is_approximate_and_positive(self):
        self.assertEqual(approx_walk_minutes(0), 1)
        self.assertEqual(approx_walk_minutes(750), 13)  # 750*1.3/75 = 13

    def test_reach_shrinks_with_return_trip(self):
        self.assertGreater(max_reachable_distance_m(60, 20, False), max_reachable_distance_m(60, 20, True))
        self.assertEqual(max_reachable_distance_m(10, 20, True), 0)


class HoursTests(unittest.TestCase):
    def test_open_closed_unknown(self):
        self.assertEqual(status_at("Mo-Su 09:00-21:00", MONDAY_14).status, "open")
        self.assertEqual(status_at("Mo-Su 09:00-21:00", MONDAY_14).minutes_until_close, 420)
        self.assertEqual(status_at("Tu-Su 10:00-18:00; Mo off", MONDAY_14).status, "closed")
        self.assertEqual(status_at("Tu-Su 10:00-18:00; Mo off", TUESDAY_14).status, "open")
        self.assertEqual(status_at("Mo-Fr 08:00-20:00; PH off", MONDAY_14).status, "unknown")
        self.assertEqual(status_at(None, MONDAY_14).status, "not_listed")
        self.assertEqual(status_at("24/7", MONDAY_14).status, "open")

    def test_overnight(self):
        late = datetime(2026, 10, 20, 2, 0, tzinfo=config.ASTANA_TZ)  # Tue 02:00
        st = status_at("Mo-Su 18:00-04:00", late)
        self.assertEqual((st.status, st.minutes_until_close), ("open", 120))
        self.assertEqual(status_at("Mo-Su 18:00-04:00", MONDAY_14).status, "closed")

    def test_labels_never_claim_certainty(self):
        self.assertIn("may be out of date", status_at("24/7", MONDAY_14).label("en"))
        self.assertIn("could not check", status_at("PH off", MONDAY_14).label("en"))
        self.assertIn("не указаны", status_at(None, MONDAY_14).label("ru"))


class TextTests(unittest.TestCase):
    def test_language(self):
        self.assertEqual(detect_language("Хочу кофе"), "ru")
        self.assertEqual(detect_language("I want coffee"), "en")

    def test_intents_ru_en(self):
        self.assertIn("coffee", detect_intents("хочу тихое место с кофе и розеткой"))
        self.assertIn("kids", detect_intents("Еду с ребёнком"))
        self.assertIn("walk", detect_intents("I am near EXPO, where can I walk?"))
        self.assertIn("culture", detect_intents("музей с интерактивами"))

    def test_unsupported(self):
        self.assertEqual(set(detect_unsupported("тихое место с кофе и розеткой")), {"quiet", "sockets"})
        self.assertIn("events", detect_unsupported("any concerts or events tonight?"))

    def test_parse_minutes(self):
        cases = {"I have 45 minutes": 45, "30–60 минут": 60, "у меня 2 часа": 120, "1-2 hours": 120,
                 "полчаса": 30, "one hour with kids": 60, "есть час": 60, "1.5 h": 90, "coffee please": None}
        for text, expected in cases.items():
            self.assertEqual(parse_minutes(text), expected, text)


class DatasetTests(unittest.TestCase):
    def test_invalid_records_are_skipped(self):
        d = ds()
        self.assertTrue(d.is_synthetic)
        self.assertEqual(len(d.pois), 12)
        self.assertEqual(d.skipped, 2)  # bad coordinates + duplicate id

    def test_missing_file(self):
        with self.assertRaises(DatasetError):
            load_dataset(ROOT / "does_not_exist.json")


class RetrievalTests(unittest.TestCase):
    def test_short_walk_respects_budget(self):
        rr = retrieve(ds(), Request("I am near EXPO and have 45 minutes. Where can I walk?", *START, 120, now=MONDAY_14))
        self.assertEqual(rr.budget_min, 45)  # text wins over slider
        self.assertEqual(rr.budget_source, "text")
        ids = [c.id for c in rr.candidates]
        self.assertIn("fixture:5", ids)       # near park
        self.assertNotIn("fixture:6", ids)    # 5 km park is out of reach
        for c in rr.candidates:
            self.assertLessEqual(2 * c.walk_min, 45)

    def test_coffee_with_unsupported_details(self):
        rr = retrieve(ds(), Request("Хочу тихое место с кофе и розеткой", *START, 60, now=MONDAY_14))
        self.assertEqual(rr.lang, "ru")
        self.assertEqual(rr.candidates[0].poi["category"], "cafe")
        self.assertIn("sockets", rr.unsupported)
        self.assertIn("quiet", rr.unsupported)

    def test_family_and_closed_museum(self):
        rr = retrieve(ds(), Request("I am with a child and have 2 hours", *START, 60, now=MONDAY_14))
        ids = [c.id for c in rr.candidates]
        self.assertIn("fixture:7", ids)          # playground
        self.assertNotIn("fixture:8", ids)       # museum is closed on Monday per its hours
        self.assertGreaterEqual(rr.excluded.get("closed", 0), 1)
        rr2 = retrieve(ds(), Request("I am with a child and have 2 hours", *START, 60, now=TUESDAY_14))
        self.assertIn("fixture:8", [c.id for c in rr2.candidates])

    def test_unknown_hours_are_kept_but_flagged(self):
        rr = retrieve(ds(), Request("coffee at Gamma", *START, 60, now=MONDAY_14))
        gamma = [c for c in rr.candidates if c.id == "fixture:3"]
        self.assertTrue(gamma)
        self.assertEqual(gamma[0].hours.status, "unknown")

    def test_no_matches(self):
        rr = retrieve(ds(), Request("museum", *START, 10, now=MONDAY_14))
        self.assertEqual(rr.candidates, [])

    def test_empty_input(self):
        with self.assertRaises(EmptyRequest):
            retrieve(ds(), Request("   ", *START, 60, now=MONDAY_14))

    def test_interests_only(self):
        rr = retrieve(ds(), Request("", *START, 60, interests=["coffee"], now=MONDAY_14))
        self.assertTrue(all(c.poi["category"] == "cafe" for c in rr.candidates))

    def test_diversity_cap(self):
        rr = retrieve(ds(), Request("coffee", *START, 120, now=datetime(2026, 10, 19, 19, 0, tzinfo=config.ASTANA_TZ)))
        self.assertLessEqual(sum(c.poi["category"] == "cafe" for c in rr.candidates), 2)


class PipelineTests(unittest.TestCase):
    def test_valid_output_is_grounded(self):
        d = ds()
        llm = fake_llm({"recommendations": [
            {"id": "P1", "why": "Close by and fits a short walk.", "activity": "Walk a loop.", "visit_minutes": 999},
            {"id": "P99", "why": "invented", "activity": "x", "visit_minutes": 10},
            {"id": "osm:node/123", "why": "invented", "activity": "x", "visit_minutes": 10},
            {"id": "P1", "why": "dup", "activity": "x", "visit_minutes": 10},
        ], "note": "ok"})
        res = run(d, Request("45 minutes walk", *START, 60, now=MONDAY_14), llm_call=llm)
        self.assertIsNone(res.error)
        self.assertEqual(len(res.recommendations), 1)
        self.assertEqual(len(res.dropped), 3)
        rec = res.recommendations[0]
        self.assertIn(rec.poi["id"], d.by_id)                # authoritative record from dataset
        self.assertLessEqual(rec.visit_minutes, rec.visit_range[1])  # clamped
        self.assertLessEqual(rec.total_min, 45)
        self.assertIn("EVIDENCE", llm.user)
        self.assertNotIn(str(START[0]), llm.user)            # user coordinates are not sent to the model

    def test_real_ids_also_accepted(self):
        llm = fake_llm({"recommendations": [{"poi_id": "fixture:1", "why": "coffee", "activity": "sit", "visit_minutes": 20}]})
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=llm)
        self.assertEqual([r.poi["id"] for r in res.recommendations], ["fixture:1"])

    def test_ungrounded_claim_warning(self):
        llm = fake_llm({"recommendations": [{"id": "P1", "why": "Quiet place with power sockets, rating 4.9.",
                                             "activity": "Work", "visit_minutes": 30}]})
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=llm)
        w = res.recommendations[0].warnings
        self.assertEqual(w[0]["code"], "ungrounded")
        self.assertTrue({"quiet", "sockets", "ratings"} <= set(w[0]["claims"]))

    def test_honest_unknown_not_flagged(self):
        self.assertEqual(ungrounded_claims("Sockets and quietness are unknown in our data.", {"name": "x"}), [])

    def test_llm_failure_is_reported(self):
        def boom(system, user):
            raise LLMError("Cannot reach Ollama")
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=boom)
        self.assertEqual(res.recommendations, [])
        self.assertIn("Ollama", res.error)
        self.assertTrue(res.retrieval.candidates)  # retrieved results can still be shown, labelled

    def test_malformed_json(self):
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=fake_llm("Sure! Here you go"))
        self.assertIn("could not be parsed", res.error)

    def test_json_wrapped_in_text(self):
        txt = 'Here: {"recommendations":[{"id":"P1","why":"w","activity":"a","visit_minutes":20}]} thanks'
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=fake_llm(txt))
        self.assertEqual(len(res.recommendations), 1)

    def test_think_block_is_ignored(self):
        txt = '<think>maybe {P2}? let me see</think>{"recommendations":[{"id":"P1","why":"w","activity":"a","visit_minutes":20}]}'
        res = run(ds(), Request("coffee", *START, 60, now=MONDAY_14), llm_call=fake_llm(txt))
        self.assertIsNone(res.error)
        self.assertEqual(len(res.recommendations), 1)

    def test_no_candidates_skips_llm(self):
        def never(system, user):
            raise AssertionError("LLM must not be called without evidence")
        res = run(ds(), Request("museum", *START, 10, now=MONDAY_14), llm_call=never)
        self.assertEqual(res.recommendations, [])
        self.assertIn("No places", res.note)

    def test_mini_route(self):
        llm = fake_llm({"recommendations": [
            {"id": "P1", "why": "a", "activity": "a", "visit_minutes": 15},
            {"id": "P2", "why": "b", "activity": "b", "visit_minutes": 15}]})
        res = run(ds(), Request("walk 2 hours", *START, 60, now=MONDAY_14), llm_call=llm)
        self.assertIsNotNone(res.route)
        self.assertEqual(len(res.route.legs), 3)  # start->A, A->B, B->start


if __name__ == "__main__":
    unittest.main()
