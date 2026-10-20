"""Photos and descriptions from Wikidata / Wikimedia Commons / Wikipedia.

The HTTP layer is MOCKED with responses shaped like the real APIs (formatversion=2).
These tests prove parsing, licence checks, safety and failure handling, not that the real
services answer (that is checked on your laptop with scripts/enrich_wiki.py).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from walks.enrich import Client, EnrichError, _commons_file_from_tags, enrich_file, enrich_pois, fetch_commons, norm_file  # noqa: E402
from walks.pipeline import public_media  # noqa: E402


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, fail=False):
        self.headers, self.calls, self.fail = {}, [], fail

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        if self.fail:
            return Resp({}, 503)
        if "wikidata.org" in url:
            return Resp({"entities": {
                "Q1": {"id": "Q1", "labels": {"en": {"language": "en", "value": "Baiterek"}},
                       "descriptions": {"ru": {"language": "ru", "value": "монумент и смотровая башня"},
                                        "en": {"language": "en", "value": "monument and observation tower"}},
                       "claims": {"P18": [{"mainsnak": {"datavalue": {"value": "Baiterek tower.jpg", "type": "string"}}}]},
                       "sitelinks": {"enwiki": {"site": "enwiki", "title": "Bayterek Tower"},
                                     "ruwiki": {"site": "ruwiki", "title": "Байтерек (монумент)"}}},
                "Q2": {"id": "Q2", "labels": {}, "descriptions": {"kk": {"language": "kk", "value": "мешіт"}},
                       "claims": {"P18": [{"mainsnak": {"datavalue": {"value": "No licence.jpg"}}}]}, "sitelinks": {}},
                "Q3": {"id": "Q3", "missing": True}}})
        if "commons.wikimedia.org" in url:
            return Resp({"query": {"normalized": [{"from": "File:Baiterek_tower.jpg", "to": "File:Baiterek tower.jpg"}],
                                   "pages": [
                {"title": "File:Baiterek tower.jpg", "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Baiterek_tower.jpg/640px-Baiterek_tower.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Baiterek_tower.jpg",
                    "extmetadata": {"Artist": {"value": "<a href='//x'>Jane <b>Doe</b></a> &amp; co"},
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}}]},
                {"title": "File:No licence.jpg", "imageinfo": [{
                    "thumburl": "https://upload.wikimedia.org/x.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:No_licence.jpg",
                    "extmetadata": {}}]},
                {"title": "File:Evil.jpg", "imageinfo": [{
                    "thumburl": "javascript:alert(1)", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Evil.jpg",
                    "extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}]}})
        if "en.wikipedia.org" in url:
            return Resp({"query": {"pages": [{"title": "Bayterek Tower",
                                              "extract": "Bayterek is a monument and observation tower in Astana. " * 3}]}})
        if "ru.wikipedia.org" in url:
            return Resp({"query": {"pages": [{"title": "Байтерек (монумент)", "missing": True}]}})
        return Resp({}, 404)


def pois():
    return [
        {"id": "osm:node/1", "name": "Бәйтерек", "names": {"kk": "Бәйтерек"}, "category": "attraction",
         "osm_tags": {"wikidata": "Q1", "tourism": "attraction"}},
        {"id": "osm:way/2", "name": "Мешіт", "names": {}, "category": "worship", "osm_tags": {"wikidata": "Q2"}},
        {"id": "osm:node/3", "name": "Cafe", "names": {}, "category": "cafe",
         "osm_tags": {"image": "https://example.com/cafe.jpg"}},
        {"id": "osm:node/4", "name": "Missing", "names": {}, "category": "park", "osm_tags": {"wikidata": "Q3"}},
        {"id": "osm:node/5", "name": "Evil", "names": {}, "category": "artwork", "osm_tags": {"wikimedia_commons": "File:Evil.jpg"}},
    ]


def client(sess):
    return Client(session=sess, sleep=lambda s: None, log=lambda *a: None)


class EnrichTests(unittest.TestCase):
    def test_photo_with_licence_and_clean_author(self):
        ps = pois()
        stats = enrich_pois(ps, client(FakeSession()))
        ph = ps[0]["media"]["photo"]
        self.assertTrue(ph["thumb"].startswith("https://upload.wikimedia.org/"))
        self.assertEqual(ph["author"], "Jane Doe & co")          # HTML stripped
        self.assertEqual(ph["license"], "CC BY-SA 4.0")
        self.assertEqual(stats["photos"], 2)   # Baiterek + "Evil" (served from a safe Commons link, see below)

    def test_no_photo_without_licence_or_with_unsafe_url(self):
        ps = pois()
        enrich_pois(ps, client(FakeSession()))
        self.assertNotIn("photo", ps[1].get("media", {}))   # no licence -> not shown
        evil = ps[4]["media"]["photo"]                      # javascript: thumbnail never used...
        self.assertNotIn("javascript", json.dumps(evil))
        self.assertTrue(evil["thumb"].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/"))  # ...safe link instead
        self.assertNotIn("media", ps[2])                    # non-Commons image tag ignored
        self.assertNotIn("media", ps[3])                    # missing Wikidata entity

    def test_descriptions_wikipedia_then_wikidata(self):
        ps = pois()
        enrich_pois(ps, client(FakeSession()))
        s = ps[0]["media"]["summary"]
        self.assertEqual(s["en"]["source"], "Wikipedia")
        self.assertLessEqual(len(s["en"]["text"]), 421)
        self.assertTrue(s["en"]["url"].startswith("https://en.wikipedia.org/wiki/"))
        self.assertEqual(s["ru"]["source"], "Wikidata")      # ru article missing -> Wikidata description
        self.assertEqual(ps[1]["media"]["summary"]["kk"]["text"], "мешіт")

    def test_labels_are_stored_with_identity_never_as_osm_names(self):
        ps = pois()
        before = dict(ps[0]["names"])
        enrich_pois(ps, client(FakeSession()))
        self.assertEqual(ps[0]["names"], before)                      # name:xx values are never invented
        self.assertEqual(ps[0]["media"]["labels"]["en"], "Baiterek")  # kept separately
        self.assertIn(ps[0]["media"]["identity"]["status"], ("ok", "no_coords"))

    def test_commons_tag_parsing(self):
        self.assertEqual(_commons_file_from_tags({"wikimedia_commons": "File:A b.jpg"}), "A b.jpg")
        self.assertEqual(_commons_file_from_tags({"image": "https://commons.wikimedia.org/wiki/File:A_b.jpg"}), "A b.jpg")
        self.assertEqual(_commons_file_from_tags({"image": "https://upload.wikimedia.org/wikipedia/commons/a/ab/A_b.jpg"}), "A b.jpg")
        self.assertIsNone(_commons_file_from_tags({"image": "https://instagram.com/p/x"}))

    def test_failure_leaves_file_unchanged_and_synthetic_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "pois.json"
            original = json.dumps({"meta": {}, "pois": pois()}, ensure_ascii=False)
            f.write_text(original, encoding="utf-8")
            with self.assertRaises(EnrichError):
                enrich_file(f, client(FakeSession(fail=True)))
            self.assertEqual(f.read_text(encoding="utf-8"), original)
            stats = enrich_file(f, client(FakeSession()))
            saved = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(saved["meta"]["media"]["photos"], stats["photos"])
            f.write_text(json.dumps({"meta": {"is_synthetic": True}, "pois": []}), encoding="utf-8")
            with self.assertRaises(EnrichError):
                enrich_file(f, client(FakeSession()))

    def test_polite_requests(self):
        sess = FakeSession()
        enrich_pois(pois(), client(sess))
        self.assertIn("AstanaWalks", sess.headers["User-Agent"])
        self.assertTrue(all(p.get("format") == "json" for _, p in sess.calls))
        self.assertLessEqual(len(sess.calls), 6)             # batched, not one request per place

    def test_public_media_sanitizes(self):
        p = {"media": {"photo": {"thumb": "https://upload.wikimedia.org/a.jpg", "page": "https://commons.wikimedia.org/wiki/File:a.jpg",
                                 "license": "CC0", "license_url": "javascript:x", "author": "<script>x</script>A"},
                       "summary": {"en": {"text": "<b>Hi</b>", "source": "Evil", "url": "javascript:x"}, "xx": {"text": "no"}}}}
        m = public_media(p)
        self.assertIsNone(m["photo"]["license_url"])
        self.assertNotIn("<", m["photo"]["author"])
        self.assertEqual(m["summary"]["en"]["text"], "Hi")
        self.assertEqual(m["summary"]["en"]["source"], "Wikipedia")
        self.assertIsNone(m["summary"]["en"]["url"])
        self.assertNotIn("xx", m["summary"])
        self.assertIsNone(public_media({"media": {"photo": {"thumb": "https://evil.com/a.jpg", "page": "x", "license": "CC0"}}}))


class RealWorldShapeTests(unittest.TestCase):
    """Shapes the real APIs can return that the first version did not handle (0 photos on a real run)."""

    def test_continuation_missing_thumb_and_lowercase_names(self):
        calls = []

        class Sess:
            headers = {}

            def get(self, url, params=None, timeout=None):
                calls.append(dict(params))
                if "continue" not in params:   # first answer: metadata split, ask to continue
                    return Resp({"continue": {"iicontinue": "x", "continue": "||"},
                                 "query": {"normalized": [{"from": "File:baiterek_2.jpg", "to": "File:Baiterek 2.jpg"}],
                                           "pages": [{"title": "File:Baiterek 2.jpg"}, {"title": "File:Gone.jpg", "missing": True}]}})
                return Resp({"query": {"pages": [{"title": "File:Baiterek 2.jpg", "imageinfo": [{
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Baiterek_2.jpg",
                    "extmetadata": {"LicenseShortName": {"value": "CC BY 3.0"}, "Artist": {"value": "A"}}}]}]}})
        logs = []
        c = Client(session=Sess(), sleep=lambda s: None, log=logs.append)
        out = fetch_commons(c, ["baiterek_2.jpg", "Gone.jpg"])
        self.assertIn(norm_file("baiterek_2.jpg"), out)
        ph = out["Baiterek 2.jpg"]
        self.assertTrue(ph["thumb"].startswith("https://commons.wikimedia.org/wiki/Special:FilePath/Baiterek_2.jpg?width="))
        self.assertEqual(len(calls), 2)                                   # continuation followed
        self.assertTrue(any("1 usable photos" in l and "file not on Commons (1)" in l for l in logs), logs)

    def test_reasons_are_logged_when_nothing_is_usable(self):
        class Sess:
            headers = {}

            def get(self, url, params=None, timeout=None):
                return Resp({"query": {"pages": [{"title": "File:A.jpg", "imageinfo": [{"thumburl": "https://upload.wikimedia.org/a.jpg",
                                                                                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.jpg",
                                                                                        "extmetadata": {}}]}]}})
        logs = []
        self.assertEqual(fetch_commons(Client(session=Sess(), sleep=lambda s: None, log=logs.append), ["A.jpg"]), {})
        self.assertTrue(any("0 usable photos" in l and "no licence information (1)" in l for l in logs), logs)

    def test_wikipedia_tag_resolves_to_wikidata(self):
        class Sess(FakeSession):
            def get(self, url, params=None, timeout=None):
                if params.get("prop") == "pageprops":
                    self.calls.append((url, dict(params)))
                    return Resp({"query": {"pages": [{"title": "Байтерек (монумент)", "pageprops": {"wikibase_item": "Q1"}}]}})
                return super().get(url, params, timeout)
        ps = [{"id": "osm:node/9", "name": "Бәйтерек", "names": {}, "category": "attraction",
               "osm_tags": {"wikipedia": "ru:Байтерек (монумент)", "tourism": "attraction"}}]
        stats = enrich_pois(ps, client(Sess()))
        self.assertEqual(ps[0]["osm_tags"]["wikidata_resolved"], "Q1")
        self.assertEqual(stats["photos"], 1)


if __name__ == "__main__":
    unittest.main()
