"""Version 5 regression tests: place-name provenance, conservative de-duplication, search,
negation / named places / start conflicts, filters, clause-level grounding, structured output
and repair, plan styles, active-walk replanning, empty-result suggestions, semantic fusion.
All data here is SYNTHETIC; the model is a FAKE (no real model output is tested here)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from walks import config, grounding, names, semantic  # noqa: E402
from walks.data import load_dataset  # noqa: E402
from walks.dedup import match_reason, merge_duplicates  # noqa: E402
from walks.itinerary import Context, Stop, fit_plan  # noqa: E402
from walks.llm import LLMReply  # noqa: E402
from walks.pipeline import answer_schema, run, ungrounded_claims  # noqa: E402
from walks.retrieval import retrieve  # noqa: E402
from walks.search import Index, find_mentions  # noqa: E402
from walks.text import detect_intents, detect_negations, intents_in_order  # noqa: E402
from tests.test_planning import DS, MON_1430, START, P, explain_all, fake_llm, make_ds, req  # noqa: E402

TZ = config.ASTANA_TZ


def poi(i, name, cat="attraction", tags=None, lat=51.09, lon=71.42, **kw):
    p = {"id": f"osm:node/{i}", "name": name, "name_is_generated": False, "names": {}, "lat": lat, "lon": lon,
         "category": cat, "osm_tags": tags or {}, "opening_hours": None, "contacts": {}, "description": "",
         "description_source": "summary_of_osm_tags", "collected_at": "2026-10-19T00:00:00+00:00",
         "source_url": f"https://www.openstreetmap.org/node/{i}", "notable": False}
    p.update(kw)
    names.normalize_names(p)
    return p


class NamePolicyTests(unittest.TestCase):
    def setUp(self):
        self.old = config.NAME_OVERRIDES_PATH
        config.NAME_OVERRIDES_PATH = Path("/nonexistent/overrides.json")

    def tearDown(self):
        config.NAME_OVERRIDES_PATH = self.old

    def test_explicit_english_tag_wins(self):
        p = poi(1, "Бәйтерек", tags={"name:en": "Baiterek", "name:ru": "Байтерек"})
        self.assertEqual(names.resolve(p, "en")["text"], "Baiterek")
        self.assertEqual(names.resolve(p, "en")["kind"], "osm")
        self.assertEqual(names.resolve(p, "ru")["text"], "Байтерек")

    def test_missing_english_keeps_original_with_descriptor(self):
        p = poi(2, "Атырау көпірі", tags={"name:kk": "Атырау көпірі"})
        r = names.resolve(p, "en")
        self.assertEqual(r["text"], "Атырау көпірі")             # never "Atyrau kopiri" as a name
        self.assertEqual(r["kind"], "original")
        self.assertEqual(r["descriptor"], "Attraction")
        self.assertEqual(r["translation"], "Atyrau Bridge")     # labelled descriptive translation
        self.assertEqual(r["latin"], "Atyrau kopiri")           # pronunciation aid only
        self.assertEqual(r["lang"], "kk")                       # known only because OSM says name == name:kk

    def test_kazakh_cyrillic_without_russian_is_not_called_russian(self):
        p = poi(3, "Инжіл-лютеран шіркеуі", cat="worship")
        ru = names.resolve(p, "ru")
        self.assertEqual((ru["text"], ru["kind"], ru["lang"]), ("Инжіл-лютеран шіркеуі", "original", None))
        self.assertNotIn("translation", names.resolve(p, "en"))  # hyphenated adjective: no mechanical translation

    def test_dative_monument_name_is_not_mangled(self):
        r = names.resolve(poi(4, "А. С. Пушкину", cat="artwork"), "en")
        self.assertEqual(r["text"], "А. С. Пушкину")
        self.assertNotIn("translation", r)

    def test_latin_brand_is_not_translated(self):
        p = poi(5, "Mega Silk Way", cat="mall")
        for lang in ("kk", "ru", "en"):
            self.assertEqual(names.resolve(p, lang)["text"], "Mega Silk Way")

    def test_legacy_guessed_names_become_unverified_aliases(self):
        p = {"id": "osm:node/6", "name": "Атырау көпірі", "names": {"en": "Atyrau kopiri", "ru": "Атырау көпірі"},
             "osm_tags": {}, "category": "attraction"}
        names.normalize_names(p)
        self.assertEqual(p["names"], {})
        kinds = {a["text"]: a["kind"] for a in p["aliases"]}
        self.assertEqual(kinds.get("Atyrau kopiri"), "legacy_unverified")
        self.assertEqual(names.resolve(p, "en")["kind"], "original")

    def test_wikidata_label_only_with_identity_ok(self):
        p = poi(7, "Хан Шатыр", cat="mall", media={"labels": {"en": "Khan Shatyr Entertainment Center"},
                                                    "identity": {"status": "no_coords", "qid": "Q1"}})
        self.assertEqual(names.resolve(p, "en")["kind"], "original")
        p["media"]["identity"]["status"] = "ok"
        self.assertEqual(names.resolve(p, "en")["text"], "Khan Shatyr Entertainment Center")

    def test_identity_check_rejects_namesake_and_far_items(self):
        from walks.enrich import identity_check
        p = poi(8, "Абай", cat="artwork")
        self.assertEqual(identity_check(p, {"instance_of": ["Q5"], "coords": None})["status"], "not_place")
        self.assertEqual(identity_check(p, {"instance_of": ["Q4989906"], "coords": (51.5, 71.0)})["status"], "far")
        self.assertEqual(identity_check(p, {"instance_of": ["Q4989906"], "coords": (51.0901, 71.4201)})["status"], "ok")

    def test_overrides_need_source_and_review_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "o.json"
            f.write_text(json.dumps({"overrides": [
                {"id": "osm:node/2", "lang": "en", "text": "Atyrau Bridge", "kind": "common_name",
                 "source_url": "https://example.org/x", "reviewed": "2026-10-20"},
                {"id": "osm:node/3", "lang": "en", "text": "No source"}]}), encoding="utf-8")
            config.NAME_OVERRIDES_PATH = f
            r = names.resolve(poi(2, "Атырау көпірі"), "en")
            self.assertEqual((r["text"], r["kind"], r["source"]), ("Atyrau Bridge", "override", "https://example.org/x"))
            self.assertEqual(names.resolve(poi(3, "Без источника"), "en")["kind"], "original")

    def test_api_returns_all_languages_for_instant_switching(self):
        from walks.pipeline import _poi_public
        out = _poi_public(poi(9, "Бәйтерек", tags={"name:en": "Baiterek"}), "ru")
        self.assertEqual(set(out["display_names"]), {"kk", "ru", "en"})
        self.assertEqual(out["display_names"]["en"]["text"], "Baiterek")
        self.assertFalse(out["name_transliterated"])


class DedupTests(unittest.TestCase):
    def test_nearby_branches_of_one_brand_are_not_merged(self):
        a = poi(10, "Coffee Boom", "cafe", {"addr:housenumber": "10"}, lat=51.0900, lon=71.4200)
        b = poi(11, "Coffee Boom", "cafe", {"addr:housenumber": "24"}, lat=51.0904, lon=71.4206)
        c = poi(12, "Coffee Boom", "cafe", {}, lat=51.0906, lon=71.4210)
        self.assertIsNone(match_reason(a, b))   # different house numbers
        self.assertIsNone(match_reason(a, c))   # two separate points ~70 m apart
        self.assertEqual(merge_duplicates([a, b, c])[1], 0)

    def test_park_and_attraction_inside_are_different(self):
        self.assertIsNone(match_reason(poi(13, "Арай", "park"), poi(14, "Арай", "attraction")))

    def test_node_and_area_merge_records_reason_and_keeps_alias(self):
        a = {**poi(15, "Хан Шатыр", "mall", {"shop": "mall", "building": "yes"}), "id": "osm:way/15"}
        b = poi(16, "Khan Shatyr", "mall", {"shop": "mall"}, lat=51.0902, lon=71.4203)
        kept, n = merge_duplicates([a, b])
        self.assertEqual(n, 1)
        self.assertEqual(kept[0]["merges"][0]["reason"], "node_and_area")
        self.assertIn({"text": "Khan Shatyr", "kind": "merged_record_name", "source": "osm:node/16"}, kept[0]["aliases"])
        self.assertEqual(kept[0]["names"], {})  # not re-labelled as name:en

    def test_numbered_branches_never_merged(self):
        self.assertIsNone(match_reason(poi(17, "School 5", "campus"), {**poi(18, "School 7", "campus"), "id": "osm:way/18"}))


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.pois = [poi(20, "Бәйтерек", tags={"name:en": "Baiterek"}, lat=51.1283, lon=71.4305),
                     poi(21, "Хан Шатыр", "mall", lat=51.1323, lon=71.4040),
                     poi(22, "Astana IT University", "campus", lat=51.0905, lon=71.4180),
                     poi(23, "Арай саябағы", "park")]
        self.idx = Index(self.pois)

    def test_scripts_spelling_and_initials(self):
        top = lambda q: self.idx.search(q)[0][0]["id"] if self.idx.search(q) else None
        self.assertEqual(top("baiterek"), "osm:node/20")
        self.assertEqual(top("Байтерек"), "osm:node/20")
        self.assertEqual(top("khan shatyr"), "osm:node/21")
        self.assertEqual(top("AITU"), "osm:node/22")
        self.assertEqual(top("aray park"), "osm:node/23")     # descriptive translation alias
        self.assertEqual(self.idx.search("nowhere at all"), [])

    def test_mentions_detect_location_cue(self):
        ds = make_ds(self.pois)
        m = find_mentions(ds, "кофе рядом с Байтереком")
        self.assertEqual((m[0]["poi"]["id"], m[0]["cue"]), ("osm:node/20", True))
        m = find_mentions(ds, "I want to see Baiterek")
        self.assertEqual((m[0]["poi"]["id"], m[0]["cue"]), ("osm:node/20", False))
        self.assertEqual(find_mentions(ds, "a park and a cafe"), [])   # generic words never identify a place


class QueryUnderstandingTests(unittest.TestCase):
    def test_negations_in_three_languages(self):
        self.assertEqual(detect_negations("no cafes, just a walk")[0], ["cafe"])
        self.assertEqual(detect_negations("not a museum please")[0], ["museum"])
        self.assertEqual(detect_negations("без кафе, хочу в парк")[0], ["cafe"])
        self.assertEqual(detect_negations("мұражай емес, саябақ")[0], ["museum"])
        self.assertEqual(detect_negations("кафесіз серуен")[0], ["cafe"])
        self.assertNotIn("coffee", detect_intents("no cafes, just a walk"))

    def test_negated_category_is_a_hard_filter(self):
        rr = retrieve(DS, req("walk, but no cafes and not a park", 90))
        self.assertFalse(any(c.poi["category"] in ("cafe", "park") for c in rr.pool))
        self.assertGreater(rr.excluded.get("negated", 0), 0)

    def test_sequence_order(self):
        self.assertEqual(intents_in_order("coffee, then a short walk"), ["coffee", "walk"])
        self.assertEqual(intents_in_order("сначала прогулка, потом кофе"), ["walk", "coffee"])

    def test_multi_intent_plan_covers_both(self):
        res = run(DS, req("coffee then a short walk", 90), llm_call=fake_llm(["P1"]))
        cats = {r.poi["category"] for r in res.recommendations}
        self.assertTrue("cafe" in cats and cats & {"park", "viewpoint", "artwork", "attraction", "fountain"}, cats)
        self.assertEqual(res.recommendations[0].poi["category"], "cafe")   # "then": the asked order, if feasible

    def test_filters_known_hours_and_wheelchair(self):
        rr = retrieve(DS, req("coffee and walk", 90, known_hours_only=True))
        self.assertTrue(all(c.poi.get("opening_hours") for c in rr.pool))
        rr = retrieve(DS, req("coffee and walk", 90, wheelchair_only=True))
        self.assertEqual(rr.pool, [])
        self.assertGreater(rr.excluded.get("no_wheelchair_info", 0), 0)


class GroundingTests(unittest.TestCase):
    EV = {"extra_osm_tags": {}, "description": "Cafe", "about_from_wikipedia": ""}

    def test_honest_unknown_does_not_excuse_other_claims(self):
        text, removed = grounding.check("Free entry and a quiet cafe. Sockets are unknown.", self.EV)
        self.assertEqual(text, "Sockets are unknown.")
        self.assertEqual(set(removed), {"free", "quiet"})
        self.assertEqual(set(ungrounded_claims("Free entry and a quiet cafe. Sockets are unknown.", self.EV)), {"free", "quiet"})

    def test_supported_by_specific_fields_only(self):
        ev = {"extra_osm_tags": {"internet_access": "wlan", "fee": "no"}, "description": ""}
        self.assertEqual(grounding.check("Wi-Fi is available and entry is free.", ev)[1], [])
        # the word "quiet" in the place NAME is not evidence of quietness
        ev2 = {"extra_osm_tags": {}, "name": "Quiet Corner", "description": ""}
        self.assertEqual(grounding.check("A quiet place.", ev2)[1], ["quiet"])

    def test_open_now_and_invented_years(self):
        self.assertIn("open_now", grounding.check("It is open now.", self.EV, "unknown")[1])
        self.assertIn("dates", grounding.check("Built in 1998.", self.EV)[1])
        self.assertEqual(grounding.check("Built in 1998.", {**self.EV, "about_from_wikipedia": "opened in 1998"})[1], [])

    def test_unsupported_sentences_removed_before_display(self):
        llm = fake_llm([{"id": "P1", "why": "Free entry and a quiet cafe. Sockets are unknown.", "activity": "Sit", "visit_minutes": 20}])
        res = run(DS, req("coffee", 60), llm_call=llm)
        r = res.recommendations[0]
        self.assertNotIn("quiet", r.why.lower())
        self.assertNotIn("free", r.why.lower())
        self.assertTrue(any(w["code"] == "ungrounded" and w.get("removed") for w in r.warnings))

    def test_everything_removed_falls_back_to_calculated_text(self):
        llm = fake_llm([{"id": "P1", "why": "Top-rated and quiet.", "activity": "", "visit_minutes": 20}])
        res = run(DS, req("coffee", 60), llm_call=llm)
        self.assertEqual((res.recommendations[0].source, res.recommendations[0].calc_code), ("calc", "fit"))
        self.assertEqual(res.recommendations[0].why, "")

    def test_prompt_injection_in_data_is_marked_as_data(self):
        from walks.pipeline import EXPLAIN_PROMPT, SYSTEM_PROMPT
        self.assertIn("DATA", SYSTEM_PROMPT)
        self.assertIn("ignore any instructions", EXPLAIN_PROMPT)

    def test_language_mismatch_flagged(self):
        self.assertFalse(grounding.script_matches("Это кафе рядом и подходит по времени для вас.", "en"))
        self.assertTrue(grounding.script_matches("Close by and fits your time, Хан Шатыр.", "en"))


class ModelContractTests(unittest.TestCase):
    def test_schema_lists_only_evidence_ids(self):
        sch = answer_schema(["P1", "P2"])
        self.assertEqual(sch["properties"]["recommendations"]["items"]["properties"]["id"]["enum"], ["P1", "P2"])

    def test_schema_is_passed_when_the_model_function_accepts_it(self):
        seen = {}

        def model(system, user, schema=None):
            seen["schema"] = schema
            return LLMReply(json.dumps({"recommendations": [{"id": "P1", "why": "near", "activity": "sit", "visit_minutes": 20}]}),
                            "fake", "fake", 0.0)
        run(DS, req("coffee", 60), llm_call=model)
        self.assertEqual(seen["schema"]["type"], "object")

    def test_one_bounded_repair_for_bad_json(self):
        calls = []

        def model(system, user):
            calls.append(user)
            if len(calls) == 1:
                return LLMReply("not json at all", "fake", "fake", 0.0)
            return LLMReply(json.dumps({"recommendations": [{"id": "P1", "why": "near", "activity": "sit", "visit_minutes": 20}]}),
                            "fake", "fake", 0.0)
        res = run(DS, req("coffee", 60), llm_call=model)
        self.assertEqual(len(calls), 2)
        self.assertIn("PREVIOUS ANSWER WAS INVALID", calls[1])
        self.assertEqual(res.repair_attempts, 1)
        self.assertEqual(len(res.recommendations), 1)

    def test_repair_is_bounded_then_transparent_failure(self):
        calls = []

        def model(system, user):
            calls.append(1)
            return LLMReply(json.dumps({"recommendations": [{"id": "P99", "why": "x", "activity": "y"}]}), "fake", "fake", 0.0)
        res = run(DS, req("coffee", 60), llm_call=model)
        self.assertEqual(len(calls), 2)                     # one try + one repair, never more
        self.assertEqual(res.recommendations, [])
        self.assertEqual(res.note_code, "model_empty")      # shown as a failure + search-only list
        self.assertTrue(res.retrieval.candidates)


class OllamaClientTests(unittest.TestCase):
    def test_schema_sent_as_format_and_fallback_to_json(self):
        from unittest import mock
        from walks import llm
        calls = []

        class R:
            def __init__(self, code, text, content=None):
                self.status_code, self.text, self._c = code, text, content

            def json(self):
                return {"message": {"content": self._c}}

        def post(url, json=None, timeout=None):
            calls.append(json["format"])
            if isinstance(json["format"], dict):
                return R(400, "invalid format: schema not supported")
            return R(200, "", '{"recommendations": []}')
        with mock.patch.object(llm.requests, "post", side_effect=post):
            reply = llm._ollama("s", "u", {"type": "object"})
        self.assertEqual(calls, [{"type": "object"}, "json"])
        self.assertEqual(reply.text, '{"recommendations": []}')


class ItineraryAnchorTests(unittest.TestCase):
    def test_return_goes_to_the_original_start_not_the_current_position(self):
        here = (51.0910, 71.4160)          # e.g. the cafe the user just visited
        ctx = Context(here[0], here[1], "here", 75.0, True, 60, MON_1430, return_lat=START[0], return_lon=START[1],
                      return_name="AITU")
        plan, _, _ = fit_plan([Stop(DS.get("syn:3"), 15, 0)], ctx)
        self.assertEqual(plan.legs[-1]["to"], "return")
        self.assertEqual(plan.legs[-1]["to_name"], "AITU")
        from walks.geo import approx_walk_minutes, haversine_m
        p3 = DS.get("syn:3")
        self.assertEqual(plan.legs[-1]["walk_min"], approx_walk_minutes(haversine_m(p3["lat"], p3["lon"], *START), 75.0))


class ApiV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "pois.json"
        photo = {"photo": {"thumb": "https://upload.wikimedia.org/x.jpg", "page": "https://commons.wikimedia.org/wiki/File:X.jpg",
                           "author": "Test", "license": "CC BY-SA 4.0"}}
        unlicensed = {"photo": {"thumb": "https://upload.wikimedia.org/y.jpg", "page": "https://commons.wikimedia.org/wiki/File:Y.jpg"}}
        extra = [{**P(100, "attraction", 0.039, 0.0145, name="Бәйтерек", tags={"name:en": "Baiterek"}), "media": photo},
                 {**P(103, "park", 0.001, 0.003, name="Unlicensed photo park"), "media": unlicensed},
                 P(101, "cafe", 0.0018, -0.001, name="Coffee Boom", tags={"addr:housenumber": "1"}),
                 P(102, "cafe", 0.0022, -0.0005, name="Coffee Boom", tags={"addr:housenumber": "9"})]
        path.write_text(json.dumps({"meta": {"is_synthetic": True}, "pois": DS.pois + extra}, ensure_ascii=False), encoding="utf-8")
        cls.old = config.DATA_PATH, config.WEATHER_ENABLED, server.CLOCK
        config.DATA_PATH, config.WEATHER_ENABLED = path, False
        server.CLOCK = lambda: datetime(2026, 10, 19, 14, 30, tzinfo=TZ)

    @classmethod
    def tearDownClass(cls):
        config.DATA_PATH, config.WEATHER_ENABLED, server.CLOCK = cls.old
        cls.tmp.cleanup()

    def body(self, **kw):
        b = {"text": "coffee and a walk", "lang": "en", "start": {"type": "coords", "lat": START[0], "lon": START[1]},
             "budget": 120, "back": True, "weather": False}
        b.update(kw)
        return b

    def test_gallery_only_licensed_photos_and_a_stable_daily_pick(self):
        st, r = server.gallery()
        self.assertEqual(st, 200)
        self.assertEqual(r["date"], "2026-10-19")
        self.assertEqual([i["id"] for i in r["items"]], ["syn:100"])        # a photo without a licence is never shown
        for it in r["items"]:
            self.assertTrue(it["media"]["photo"]["license"] and it["media"]["photo"]["thumb"].startswith("https://"))
        if r["items"]:
            self.assertEqual(server.gallery()[1]["day"]["id"], r["day"]["id"])      # same pick all day
        old = server.CLOCK
        try:
            picks = set()
            for d in range(1, 15):
                server.CLOCK = lambda d=d: datetime(2026, 11, d, 9, 0, tzinfo=TZ)
                day = server.gallery()[1]["day"]
                if day:
                    picks.add(day["id"])
            self.assertTrue(len(picks) >= 1)
        finally:
            server.CLOCK = old

    def test_places_search_endpoint(self):
        st, r = server.places("baiterek")
        self.assertEqual(st, 200)
        self.assertEqual(r["results"][0]["display_names"]["en"]["text"], "Baiterek")
        self.assertEqual(server.places("zzzz")[1]["results"], [])

    def test_start_conflict_asks_once(self):
        b = self.body(text="coffee near Baiterek", start={"type": "landmark", "id": "syn:1"})
        st, r = server.recommend(b, llm_call=fake_llm(["P1"]))
        self.assertEqual(r["clarify"]["code"], "start_conflict")
        self.assertIsNone(r["plan"])
        st, r = server.recommend({**b, "start_choice": "keep"}, llm_call=fake_llm(["P1"]))
        self.assertIsNotNone(r["plan"])

    def test_unreachable_named_place_is_explained(self):
        st, r = server.recommend(self.body(text="I want to see Baiterek", budget=30), llm_call=fake_llm(["P1"]))
        ex = r["understood"]["named_excluded"]
        self.assertEqual((ex[0]["id"], ex[0]["reason"]), ("syn:100", "too_far"))
        self.assertGreater(ex[0]["walk_min"], 30)

    def test_weak_cue_words_do_not_trigger_a_question(self):
        b = self.body(text="у нас час, хочу к Байтереку", start={"type": "landmark", "id": "syn:1"})
        st, r = server.recommend(b, llm_call=fake_llm(["P1"]))
        self.assertNotIn("clarify", r)

    def test_styles_are_only_shown_when_better(self):
        st, r = server.recommend(self.body(budget=120), llm_call=fake_llm(["P1", "P2"]))
        cur = r["styles"][0] if r["styles"] else None
        for s_ in r["styles"][1:]:
            if s_["key"] == "less_walking":
                self.assertLess(s_["walk_min"], cur["walk_min"])
            if s_["key"] == "less_outdoor":
                self.assertLess(s_["outdoor_min"], cur["outdoor_min"])

    def test_named_destination_is_included_when_feasible(self):
        st, r = server.recommend(self.body(text="I want to see Baiterek", budget=180), llm_call=fake_llm(["P1"]))
        self.assertEqual(r["understood"]["named"][0]["id"], "syn:100")
        self.assertEqual(r["trace"]["candidates"][0]["poi"]["id"], "syn:100")

    def test_branches_of_one_brand_not_offered_together(self):
        st, r = server.recommend(self.body(text="coffee", budget=120), llm_call=fake_llm(["P1", "P2", "P3"]))
        names_ = [c["poi"]["name"] for c in r["trace"]["candidates"]]
        self.assertLessEqual(names_.count("Coffee Boom"), 1)

    def test_styles_satisfy_the_same_constraints(self):
        st, r = server.recommend(self.body(budget=90, outdoor={"max_min": 40}), llm_call=fake_llm(["P1", "P2"]))
        for s in r["styles"]:
            self.assertLessEqual(s["total_min"], r["plan"]["budget_min"])
            self.assertLessEqual(s["outdoor_min"], 40)
        keys = [s["key"] for s in r["styles"]]
        self.assertEqual(keys[0] if keys else "current", "current")
        self.assertEqual(len({tuple(s["stop_ids"]) for s in r["styles"]}), len(r["styles"]))   # no duplicates

    def test_style_switch_explains_only_new_stops(self):
        st, r = server.recommend(self.body(budget=90), llm_call=fake_llm(["P1"]))
        keep = [s["id"] for s in r["plan"]["stops"]]
        other = next(c["poi"]["id"] for c in r["trace"]["candidates"] if c["poi"]["id"] not in keep)
        st, r2 = server.replan(self.body(budget=90, plan_stops=[{"id": keep[0], "visit_minutes": 20}, {"id": other, "visit_minutes": 15}],
                                         explain=True, keep_ids=keep), llm_call=explain_all())
        by = {s["id"]: s["text_source"] for s in r2["plan"]["stops"]}
        self.assertEqual(by[other], "ai")
        self.assertEqual(by[keep[0]], "keep")

    def test_active_walk_replan_keeps_return_anchor_and_remaining_time(self):
        st, r = server.replan(self.body(text="", budget=40, start={"type": "landmark", "id": "syn:1"},
                                        return_to={"type": "coords", "lat": START[0], "lon": START[1]},
                                        plan_stops=[{"id": "syn:3", "visit_minutes": 15}]))
        self.assertEqual(st, 200)
        plan = r["plan"]
        self.assertEqual(plan["legs"][0]["from"], "start")      # from the current position (syn:1)
        self.assertEqual(plan["legs"][-1]["to"], "return")      # back to the ORIGINAL start
        self.assertLessEqual(plan["total_min"], 40)

    def test_active_walk_with_deadline_recomputes_from_now(self):
        dl = {"enabled": True, "at": "2026-10-19T15:00", "buffer_min": 5}
        st, r = server.replan(self.body(text="", budget=120, deadline=dl, start={"type": "landmark", "id": "syn:1"},
                                        return_to={"type": "coords", "lat": START[0], "lon": START[1]},
                                        plan_stops=[{"id": "syn:3", "visit_minutes": 15}]))
        self.assertEqual(r["constraints"]["budget_min"], 25)      # 30 min left - 5 min buffer, never the old 120

    def test_empty_result_suggestions_never_drop_deadline(self):
        st, r = server.recommend(self.body(text="museum", budget=10), llm_call=fake_llm(["P1"]))
        keys = [s["key"] for s in r["suggestions"]]
        self.assertIn("add_time", keys)
        dl = {"enabled": True, "at": "2026-10-19T14:50", "buffer_min": 5}
        st, r = server.recommend(self.body(text="museum", deadline=dl), llm_call=fake_llm(["P1"]))
        keys = [s["key"] for s in r["suggestions"]]
        self.assertIn("deadline_binding", keys)
        self.assertNotIn("add_time", keys)

    def test_filters_validated_and_reported(self):
        st, r = server.recommend(self.body(filters={"known_hours": "yes"}), llm_call=fake_llm(["P1"]))
        self.assertEqual((st, r["error"]["code"]), (400, "bad_filters"))
        st, r = server.recommend(self.body(filters={"known_hours": True}), llm_call=fake_llm(["P1"]))
        self.assertTrue(all(s["poi"]["opening_hours"] for s in r["plan"]["stops"]))

    def test_fit_facts_and_timings(self):
        st, r = server.recommend(self.body(text="coffee with a power socket"), llm_call=fake_llm(["P1"]))
        f = r["plan"]["stops"][0]["fit"]
        self.assertIn("coffee", f["interests"])
        self.assertIn("sockets", f["unknown"])
        self.assertIn("retrieval", r["trace"]["timings_ms"])
        self.assertEqual(r["trace"]["retrieval_mode"], "lexical")


class SemanticFusionTests(unittest.TestCase):
    def tearDown(self):
        semantic.set_encoder(None)
        config.RETRIEVAL_MODE = "lexical"

    def test_hybrid_reranks_only_eligible_places_with_rrf(self):
        def enc(texts):
            # FAKE encoder: one axis for viewpoint documents and for queries that mention a panorama
            return [[1.0, 0.0] if ("viewpoint" in t.lower() or "panorama" in t.lower()) else [0.0, 1.0] for t in texts]
        enc.is_fake = True
        semantic.set_encoder(enc)
        config.RETRIEVAL_MODE = "hybrid"
        rr = retrieve(DS, req("walk with a panorama", 120))
        self.assertEqual(rr.mode, "hybrid")
        self.assertGreater(len(rr.pool), 1)
        self.assertIn("rrf", rr.pool[0].parts)
        self.assertEqual(rr.pool[0].poi["category"], "viewpoint")          # semantic rank fused in
        self.assertTrue(all(c.poi["category"] in rr.target_categories for c in rr.pool))  # filters still first

    def test_unavailable_model_falls_back_and_says_so(self):
        semantic.set_encoder(None)
        config.RETRIEVAL_MODE = "hybrid"
        rr = retrieve(DS, req("coffee", 60))
        try:
            import sentence_transformers  # noqa: F401
            installed = True
        except Exception:
            installed = False
        if not installed:
            self.assertEqual(rr.mode, "lexical")
            self.assertIn("not installed", rr.mode_note)


class DataPipelineTests(unittest.TestCase):
    def test_invalid_records_skipped_with_reasons(self):
        good = poi(30, "Good")
        bad_url = {**poi(31, "Bad"), "source_url": "javascript:alert(1)"}
        bad_id = {**poi(32, "Bad id"), "id": "evil id"}
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "p.json"
            f.write_text(json.dumps({"meta": {"schema_version": 2}, "pois": [good, bad_url, bad_id]}), encoding="utf-8")
            ds = load_dataset(f)
        self.assertEqual(len(ds.pois), 1)
        self.assertEqual(ds.skip_reasons, {"bad_source_url": 1, "bad_id": 1})
        self.assertEqual(ds.schema_version, 2)

    def test_backup_before_save(self):
        from walks.osm_collect import save_atomic
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "pois.json"
            f.write_text('{"meta": {}, "pois": []}', encoding="utf-8")
            save_atomic({"meta": {}, "pois": [1]}, f)
            backups = list((Path(tmp) / "backups").glob("pois-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text())["pois"], [])

    def test_report_counts(self):
        from walks.report import data_quality, naming_audit
        ds = make_ds([poi(40, "Атырау көпірі"), poi(41, "Mega Silk Way", "mall"), poi(42, "Бәйтерек", tags={"name:en": "Baiterek"})])
        na = naming_audit(ds)
        self.assertEqual(na["display_name_source_by_language"]["en"], {"original": 2, "osm": 1})
        self.assertEqual(na["english_original_name_fallback"], 1)       # only the Cyrillic one needs attention
        self.assertEqual(na["english_with_descriptive_translation"], 1)
        self.assertEqual(data_quality(ds)["opening_hours"]["missing"], 3)


if __name__ == "__main__":
    unittest.main()


class LiveEvalFindingsTests(unittest.TestCase):
    """Regressions for the defects found by the user's live evaluation on 504 real places (2026-10-20)."""

    def test_kazakh_spelling_and_case_of_a_named_place(self):
        # kk04: "Хазірет Сұлтан мешітін көргім келеді" did not find "Хазрет Султан мешіті" (spelling + accusative)
        ps = [poi(1, "Хазрет Султан мешіті", "worship", lat=51.125, lon=71.472), poi(2, "Мега Силк Вей", "mall")]
        m = find_mentions(make_ds(ps), "Хазірет Сұлтан мешітін көргім келеді")
        self.assertEqual([x["poi"]["id"] for x in m], ["osm:node/1"])
        self.assertFalse(m[0]["cue"])                 # a destination, not a start: no question

    def test_tight_outdoor_limit_without_interest_means_indoors(self):
        # en08/kk08: "it's freezing, somewhere warm" with a 10-minute outdoor limit returned outdoor types
        for text in ("it's freezing, somewhere warm", "сыртта суық, жылы жер керек", "something nice nearby"):
            rr = retrieve(DS, req(text, 60, outdoor_max=10))
            self.assertIn("indoor", rr.intents, text)
            self.assertTrue(set(rr.target_categories) <= {"mall", "cafe", "museum", "gallery", "arts_centre", "library", "cinema"},
                            rr.target_categories)

    def test_styles_use_a_diverse_candidate_slice(self):
        # en13: the top 8 of the pool could all be one type, so "coffee + walk" had no alternatives
        from walks.styles import style_candidates
        class C:
            def __init__(self, i, cat): self.poi = {"id": str(i), "category": cat, "name": f"n{i}"}
        pool = [C(i, "cafe") for i in range(10)] + [C(10 + i, "park") for i in range(4)]
        cats = [c.poi["category"] for c in style_candidates(pool)]
        self.assertEqual(cats.count("cafe"), 3)
        self.assertEqual(cats.count("park"), 3)

    def test_styles_report_why_there_are_none(self):
        res = run(DS, req("coffee", 60), llm_call=fake_llm(["P1"]))
        self.assertIsNotNone(res.plan)
        self.assertIn(res.styles_status, ("ok", "no_other_feasible_plan", "current_is_best"))
        if not res.styles:
            self.assertNotEqual(res.styles_status, "ok")

    def test_cross_script_chain_names_are_one_chain(self):
        from walks.retrieval import chain_key
        self.assertEqual(chain_key({"name": "Кофе Бум"}), chain_key({"name": "Coffee Boom"}))

    def test_flight_and_late_hour_notices(self):
        from walks.pipeline import to_dict
        res = run(DS, req("2 hours before my flight, what to see?", 120), llm_call=fake_llm(["P1"]))
        self.assertTrue(to_dict(res, {})["understood"]["flight"])
        late = run(DS, req("something unusual, maybe a rooftop", 90, now=MON_1430.replace(hour=23)), llm_call=fake_llm(["P1"]))
        u = to_dict(late, {})["understood"]
        self.assertTrue(u["late_hour"])
        self.assertIn("rooftop", u["unsupported"])

    def test_rooftop_and_interactive_claims_need_evidence(self):
        ev = {"extra_osm_tags": {}, "description": "Museum", "about_from_wikipedia": ""}
        self.assertEqual(set(grounding.check("Go up to the rooftop. Interactive exhibits for kids.", ev)[1]),
                         {"rooftop", "interactive"})
        ev2 = {**ev, "about_from_wikipedia": "An interactive science museum."}
        self.assertEqual(grounding.check("Interactive exhibits for kids.", ev2)[1], [])

    def test_output_is_capped_and_short_fields_are_required(self):
        from walks import llm as L
        self.assertGreater(config.LLM_NUM_PREDICT, 0)
        sch = answer_schema(["P1"])
        self.assertEqual(sch["properties"]["recommendations"]["items"]["properties"]["why"]["maxLength"], 320)
        from unittest import mock

        class R:
            status_code, text = 200, ""
            def json(self):
                return {"message": {"content": "{}"}, "eval_count": 700, "prompt_eval_count": 1800, "done_reason": "length"}
        sent = {}

        def post(url, json=None, timeout=None):
            sent.update(json["options"])
            return R()
        with mock.patch.object(L.requests, "post", side_effect=post):
            reply = L._ollama("s", "u", {"type": "object"})
        self.assertEqual(sent["num_predict"], config.LLM_NUM_PREDICT)
        self.assertEqual((reply.output_tokens, reply.done_reason), (700, "length"))

    def test_long_kazakh_evidence_is_trimmed_to_fit_the_context(self):
        from walks.pipeline import fit_evidence
        ev = [{"id": f"P{i}", "name": "Саябақ", "description": "сипаттама " * 40, "about_from_wikipedia": "мәтін " * 80}
              for i in range(6)]
        out = fit_evidence(ev, budget=2500)
        self.assertLessEqual(len(out), 2600)
        self.assertEqual(out.count('"id"'), 6)       # no place is dropped by trimming

    def test_model_timeout_offers_labelled_app_choice_with_same_constraints(self):
        from walks.llm import LLMError
        from walks.pipeline import run_app_choice

        def timeout(system, user):
            raise LLMError("Ollama did not answer within 120 s", "timeout", seconds=120)
        failed = run(DS, req("coffee and a walk", 60, outdoor_max=30), llm_call=timeout)
        self.assertEqual(failed.error_code, "timeout")
        self.assertIsNone(failed.plan)
        fb = run_app_choice(DS, req("coffee and a walk", 60, outdoor_max=30))
        self.assertEqual(fb.mode, "app_choice")
        self.assertIn({"code": "app_choice"}, fb.notices)
        self.assertTrue(all(r.source == "calc" and r.calc_code in ("ranked", "group_cover") for r in fb.recommendations))
        self.assertLessEqual(fb.plan.total_min, 60)
        self.assertLessEqual(fb.plan.outdoor_min, 30)

    def test_group_of_five_is_allowed(self):
        from walks.constraints import resolve
        c = resolve({"group": {"participants": [{"minutes": 30 + i} for i in range(5)]}}, MON_1430)
        self.assertEqual((len(c.participants), c.budget_min), (5, 30))


class EvaluatorTests(unittest.TestCase):
    def test_missing_start_uses_documented_simulated_point_not_a_dataset_place(self):
        sys.path.insert(0, str(ROOT / "eval"))
        import run_eval
        ds = make_ds([poi(1, "Synthetic cafe", "cafe")])
        start, label, kind = run_eval.resolve_start(ds, "EXPO")
        self.assertEqual((start["type"], kind), ("coords", "simulated"))
        self.assertIn("SIMULATED", label)
        with self.assertRaises(SystemExit):
            run_eval.resolve_start(ds, "Unknown Place")
