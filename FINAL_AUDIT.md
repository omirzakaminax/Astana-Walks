# Astana Walks — final pre-submission audit (version 5.2, 2026-10-20)

**Verdict: ready for a local demo after specific checks on your laptop.** Nothing found blocks the demo.
The fixes made in this audit (model output cap, Kazakh name matching, plan styles, evaluator) were
verified here only with synthetic data and a fake model, so re-run the live evaluation once
(section 9). Two items are still open: the GitHub repository with your real `data/pois.json`, and
the YouTube video.

## Evidence kinds used below

| Code | Meaning |
|---|---|
| **SRC** | source inspection (read the code) |
| **UNIT** | automated tests on synthetic fixtures with a fake model (`python -m unittest discover -s tests`: 179 passed) |
| **BROWSER** | headless Chromium on synthetic data with a FAKE model and a Leaflet stub (`tests/e2e/browser_check.py`: 69/69 passed) |
| **EVAL-FIX** | `eval/run_eval.py` on the synthetic fixture, no model |
| **REAL** | your runs on your laptop, real data (502 → 504 places) and `qwen3:4b-instruct`: `doctor.py --infer`, `run_eval.py --live` (twice, versions 5.0 and 5.1) |
| **UNVERIFIED** | could not be executed here (no internet, no real dataset, no Ollama, no real browser features) |

## 1. Requirements of the brief (Case 1, НИЦ Smart City)

### Mandatory

| Requirement | Where / observable behaviour | Evidence | Status |
|---|---|---|---|
| Product concept, audience, use cases | `docs/CONCEPT.md`, slides 1–2 | SRC | PASS |
| Interactive prototype on several scenarios (real or simulated locations) | `server.py` + `web/`: start from a dataset place, a map point, typed coordinates or geolocation | BROWSER; REAL (your app runs) | PASS (geolocation prompt UNVERIFIED) |
| Automated POI collection by the team | `scripts/collect_osm.py --all` (Overpass, 3 areas + citywide sights), `scripts/enrich_wiki.py` | REAL: 502 places collected 2026-10-20, 504 in the second run | PASS |
| Data: name, coordinates, description, category/tags, hours/contacts if present | `walks/osm_collect.py`, validated on load (`walks/data.py`) | UNIT; REAL (`doctor.py`: 502 loaded, no skips reported) | PASS |
| Real RAG: retrieval from own data → model → grounded answer | `walks/retrieval.py` → `pipeline.build_evidence` → Ollama with a JSON Schema → `validate_output` + `grounding.check` → itinerary | UNIT; REAL (valid source IDs 33/33 in both live runs) | PASS |
| 1–3 places, short "why", approximate visit time, what to do | cards: AI "why" + "what to do" (labelled), calculated "How it fits", visit minutes from the itinerary | UNIT, BROWSER; REAL | PASS |
| Clear which data was used; no confident claims without data | "What we understood" chips, source links, hours "according to OSM", unknowns listed, unsupported sentences removed | UNIT, BROWSER | PASS |
| Test scenarios document | `docs/TEST_SCENARIOS.md` (+ `docs/EVALUATION.md`) | SRC | PASS |
| 5–7 min presentation (problem, audience, business, demo, RAG, limits, risks, plan) | `presentation/Astana_Walks_pitch.pdf` (10 slides, 128 KB) + `.pptx` | rendered and inspected | PASS |
| Ethics and privacy notes | `docs/CONCEPT.md` §Ethics, slide 8, page footer | SRC | PASS |
| Demo video on YouTube, accessible by link | `docs/DEMO_SCRIPT.md` | — | **TO DO (you)** |
| Repository link | — | — | **TO DO (you)**: push including `data/pois.json` |

### Illustrative examples from the brief (treated as test scenarios, not as dataset facts)

Museums, rooftops and events named in the brief are **not** added as data. Rooftop access and
events are reported as unknown; any AI text claiming them is removed (section 5).

### Optional / stretch (implemented, honestly scoped)

Weather (Open-Meteo, for the dataset area only), group planning (**2–5 people**; the brief suggests
3–5, so the limit was raised from 4 to 5 in this audit), alternative plans, external walking
directions on click, active walk, offline export, City Bingo, local problem reports, optional
hybrid retrieval (off by default, never run with a real embedding model: UNVERIFIED).

## 2. Jury criteria, in the published order (no weights assumed)

Detailed traceability: `docs/REQUIREMENTS_CHECKLIST.md`. Summary:

1. **Relevance** — hard filters in code + ranking; REAL category Hit@5 0.87 (n = 23) and 0.875 (n = 24).
   Two live-run defects fixed (indoor wish, Kazakh name variant); not yet re-measured.
2. **Context and constraints** — time, deadline + buffer, pace, group, outdoor cap, exclusions,
   negations, source filters, return point; REAL: 0 hard-constraint violations in 29 plans (twice).
3. **Explanation quality** — grounded AI text, calculated facts, source badges; REAL: 3 unsupported
   claims removed in run 1. Kazakh quality: needs a native speaker (UNVERIFIED).
4. **Understandable UX** — searchable picker, map start, one plan, styles, recovery after errors,
   three languages, themes, low-vision, phone width (BROWSER).
5. **Creativity** — styles, "I'm here", Surprise, Bingo, freeze limit, names with provenance.
6. **Ethics/privacy** — section 7.
7. **Completeness** — sections 1, 9 and 10.

## 3. Real data, names and sources

| Check | Result | Evidence |
|---|---|---|
| Genuine collected dataset | 502 places (run 1), 504 (run 2), collected 2026-10-20 from OSM | REAL |
| Stable IDs, source links | `osm:<type>/<id>` + `https://www.openstreetmap.org/...`, validated on load (bad IDs/URLs skipped and counted) | UNIT, SRC |
| Coordinates, categories, text | validated (inside Astana, known category or `other`, control characters stripped, length limits) | UNIT |
| Duplicates vs branches | merges only node+area / cross-script / same point < 30 m, each with a reason; branches with different house numbers or 70 m apart stay separate; one branch per chain per plan (also across scripts, e.g. "Кофе Бум"/"Coffee Boom", fixed in this audit) | UNIT |
| Timestamps | `collected_at` per record = download date; the UI and docs say it is **not** a verification date | SRC |
| Source terms | OSM ODbL attribution in the page and exports; Wikimedia photos only with author + licence; Wikipedia CC BY-SA / Wikidata CC0; Open-Meteo CC BY; no Google Maps / 2GIS scraping (2GIS only as an external link) | SRC |
| Unknown attributes | hours, contacts, ratings, accessibility, sockets, quietness, prices, events, rooftop access stay unknown unless an OSM tag exists | UNIT |
| Names on every surface | one resolver (`walks/names.py`) sent by the API for kk/ru/en → picker, cards, map titles, timeline, route, export, Bingo, styles, clarification | BROWSER: language switch keeps card, route and export identical |
| Real-data naming | English: 95 of 478 named places from `name:en`, 383 original + type, 13 legacy names demoted | REAL (`data_report.py`) |
| Wikidata labels as names | only after the identity check, which is **not stored yet** in your file → no Wikidata names shown | REAL (`doctor.py` WARN) — run `enrich_wiki.py` |

## 4. A request traced through the system (source inspection + tests)

`POST /api/recommend` → `server._prepare` (validates start, `constraints.resolve`, start-conflict
check `search.find_mentions`) → `retrieval.retrieve` (`_hard_filters`: exclusions, negated types,
type, source filters, reachability at pace, hours at arrival for the minimum visit, outdoor cap;
then BM25 + type + proximity, diverse top 6) → `pipeline.build_evidence` (IDs P1–P6, names from
`names.resolve`, no coordinates) → `llm.generate` (JSON Schema allowing only P1–P6, `num_predict`
cap) → `_model_answer` (≤ 1 repair) → `validate_output` (IDs, duplicates, clamps, clause-level
`grounding.check` removes unsupported sentences) → `itinerary.fit_plan` (one canonical plan,
re-checks hours and limits) → `to_dict` (POI facts + `fit` calculated facts + AI text with
`text_source`). Every rendered stop is a dataset POI with an OSM source link.

Grounding regression (required): `"Free entry and a quiet cafe. Sockets are unknown."` → free entry
and quietness removed, the honest sentence kept (`test_honest_unknown_does_not_excuse_other_claims`,
`test_unsupported_sentences_removed_before_display`). PASS (UNIT).

## 5. Features end to end

| Feature | UI → API → backend → output | Evidence | Status |
|---|---|---|---|
| Start search / map selection | picker → `GET /api/places` → `search.Index`; map click → coords start | BROWSER (map via stub) | PASS (real tiles UNVERIFIED) |
| Multilingual requests, negations, order | text → `text.py` → hard filters / coverage | UNIT | PASS |
| Named places (destination / start conflict) | text → `find_mentions` → named bonus or one question; unreachable → reason shown | UNIT, BROWSER | PASS (Kazakh variant fixed; REAL re-run pending) |
| Explanations | AI text grounded; "How it fits" calculated | UNIT, BROWSER | PASS |
| Deadline + buffer | More options → `constraints.parse_deadline` → cap; countdown | UNIT, BROWSER | PASS |
| Pace | 45/75/95 m/min, request-scoped | UNIT (concurrency) | PASS |
| Weather / outdoor limit | Open-Meteo area weather re-ranks; outdoor cap is hard | UNIT | PASS (live weather UNVERIFIED) |
| Replace / visited / closed / too far / remove | card → `/api/replace` or `/api/replan` | UNIT, BROWSER, REAL (replacement kept others) | PASS |
| Surprise me | `mode=surprise` | UNIT, BROWSER | PASS |
| Group 2–5 | More options → shortest time, slowest pace, coverage | UNIT, BROWSER | PASS |
| Alternative plans | `styles` + `styles_status` | UNIT, BROWSER, EVAL-FIX (2 alternatives); REAL showed 0 before the fix | PASS after fix (REAL re-run pending) |
| Directions hand-off | Google `api=1&travelmode=walking`, OSM foot routing; on click; private start only with consent | UNIT (Node), BROWSER | PASS (opening on a phone UNVERIFIED) |
| Active walk | mark done → `/api/replan` with `return_to` | UNIT, BROWSER, REAL (returned to original start, within remaining time) | PASS |
| Copy / share / offline HTML | `plan.js` | UNIT (Node), BROWSER | PASS (Windows clipboard/download UNVERIFIED) |
| Visited memory, passport, Bingo | localStorage, opt-in | BROWSER | PASS |
| Problem reports | local JSON download, no coordinates/query | BROWSER | PASS |
| Model failure recovery | error + **Try again** + **Plan without AI text** (labelled, same constraints) + search-only list | UNIT, BROWSER (failure simulated) | PASS (added in this audit) |
| Cancel a running request | Cancel button; late answer ignored (sequence guard + AbortController) | BROWSER | PASS (added in this audit) |
| Stale responses / repeated clicks | sequence guard, buttons disabled while busy | BROWSER | PASS |

No previously promised feature is missing. Not implemented (never promised): real street routes,
accounts, live events, ratings, server-side history.

## 6. Itinerary and constraints

One `Plan` object drives stop order, durations, legs (including the return leg), totals, map,
timeline, styles and exports (UNIT `test_total_includes_all_legs_and_displayed_visits`, BROWSER
"timeline stops == cards"). Hours are checked at arrival for the whole visit in Astana time (UTC+5),
including overnight ranges (UNIT `test_overnight`, `test_hours_checked_at_arrival`). Missing hours stay
unknown. Past or too-far deadlines, a buffer larger than the time left, invalid coordinates and
impossible constraints give explicit errors; empty results list the reasons and offer one-click changes
with a preview; a deadline is never offered as something to drop (UNIT). Active-walk replanning uses
the remaining time (deadline recomputed from now) and keeps the original return point (UNIT, REAL).
Group plans use the shortest time and slowest pace (UNIT). Straight-line × 1.3 estimates are labelled.
The map caption now says the dashed line is only the order, not a street route (changed in this audit).

## 7. Scenarios

| Scenario | Expected | Evidence | Status |
|---|---|---|---|
| Near Mega Silk Way, 30–60 min walk | parks/sights within budget | eval `ru14` (added), EVAL-FIX | PASS on fixture; REAL pending |
| Quiet café with a socket | cafés; quietness and sockets "not in our data"; claims removed | UNIT, eval `en05/ru05/kk05` REAL: unknowns reported 3/3 | PASS |
| Adult with a child, playground or interactive museum | child-friendly types; "interactive" only if the place's own text says so (added) | UNIT, eval `kk15` (added) | PASS on fixture |
| Tourist, 2 hours before a flight | caveat: set the walk time yourself, airport transfer/check-in not estimated, no guarantee (added) | UNIT, eval `en14` (added) | PASS on fixture |
| Unusual late-night activity | no invented events; rooftop access unknown; late-hour safety note (added) | UNIT, eval `en15` at 23:30 (added) | PASS on fixture |
| No nearby results / incompatible filters / unknown hours | reasons + suggestions | UNIT, BROWSER | PASS |
| Geolocation denial, manual location entry | message / coordinates mode | SRC; manual entry BROWSER | denial UNVERIFIED |
| Malformed model response | one repair, then honest failure + recovery | UNIT | PASS |
| Model timeout (`kk03`, `kk11`) | output cap; recovery options | UNIT, BROWSER | fixed; REAL pending |

## 8. Usability, privacy, reliability

* Three languages including dynamic messages and errors; browser runs in KK dark, EN low-vision and
  RU at 390 px found no raw keys, no horizontal scroll and no JS errors (BROWSER). Keyboard picker (BROWSER).
* Precise coordinates stay in the browser and the request; never logged (server logs paths without
  query strings), never sent to the model, not in exports unless ticked, not in reports (SRC, BROWSER).
* External transfers only on explicit actions: map tiles/photos (OSM/Wikimedia servers see the IP),
  weather for the dataset area, directions on click, 2GIS link. No silent cloud fallback: Gemini only
  if `LLM_PROVIDER=gemini` is set (SRC). The no-AI plan is deterministic and labelled as such.
* Secrets: none in source or archive (searched for key patterns); `.env` excluded.
* Escaping: page uses `textContent`; exports escape all text; only http(s) links pass `safeUrl` (UNIT).

## 9. Commands run here (2026-10-20) and outcomes

```
python -m unittest discover -s tests                       -> Ran 179 tests, OK
node tests/js/plan_test.js                                 -> plan.js tests passed: 12
python tests/e2e/browser_check.py http://127.0.0.1:8765    -> 77/77 browser checks passed (synthetic + FAKE model)
python eval/run_eval.py --data tests/e2e/e2e_pois.json --now 2026-10-21T14:30   -> pipeline check (no model)
```

Log: `docs/test_run_log.txt`. **Not run here:** real dataset, real Ollama, real map tiles, geolocation,
Windows clipboard/download, read-aloud voices, semantic model.

**Run on your laptop (PowerShell):**

```powershell
Expand-Archive -Path "$HOME\Downloads\astana-walks.zip" -DestinationPath C:\hack -Force
cd C:\hack\astana-walks
notepad .env                       # check: OLLAMA_MODEL=qwen3:4b-instruct, LLM_NUM_PREDICT=700, LLM_NUM_CTX=6144
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python scripts\enrich_wiki.py          # stores the Wikidata identity checks
.venv\Scripts\python scripts\doctor.py --infer
.venv\Scripts\python eval\run_eval.py --live         # check kk03/kk11 (no timeout), kk04, en13 styles >= 1, en08/kk08
.venv\Scripts\python server.py                       # one full demo journey (docs/DEMO_SCRIPT.md)
```

Your existing `.env` is not overwritten by the ZIP: add `LLM_NUM_PREDICT=700` and `LLM_NUM_CTX=6144`
yourself (the code uses these defaults anyway).

## 10. Submission readiness (AI MODELS FOR SMART CITY form + brief)

| Item | State | Your step |
|---|---|---|
| GitHub link | not created by me | `git init` … push **including `data/pois.json`** (not in my ZIP because it lives on your laptop); check `.env`/`.venv` are not committed |
| Presentation ≤ 10 MB | PDF 128 KB, PPTX 53 KB | upload the PDF; replace "[YouTube link]" and "[repository link]" on the last slide first |
| Up to 5 demo files, each ≤ 100 MB | — | **check the form's accepted extensions before uploading** (I could not see the form); a ZIP of the repo without `.venv` is ≈ 1 MB plus your dataset |
| YouTube demo accessible by link | not recorded | record in daytime with `docs/DEMO_SCRIPT.md`, upload as Unlisted, open the link in a private window |
| Hosting | not required by the brief | local demo with Ollama |
| Launch instructions | `README.md` (model tag `qwen3:4b-instruct`, Windows commands) | — |

## 11. Known limitations

OSM coverage and freshness; no ratings, prices, events; straight-line walking estimates (directions
handed off); accessibility only from the OSM tag of the place; 383 places shown with their original
name in English; Kazakh texts not reviewed by a native speaker; the claim checker covers listed claim
types only; small local model ≈ 6 s per answer on your laptop; category-level evaluation labels (POI-level
labels need a human); hybrid retrieval never run with the real embedding model.

## 12. Files changed in this audit (5.1 → 5.2)

`walks/llm.py`, `walks/config.py`, `.env.example` (output cap, context size, token counts, default
model tag) · `walks/pipeline.py` (compact/trimmed evidence, short-text schema, labelled no-AI plan,
styles status, flight/late-hour flags, token trace) · `walks/search.py` (Kazakh spelling/case matching) ·
`walks/text.py` (indoor interest, flight words, rooftop unknown) · `walks/retrieval.py` (indoor default
under a tight outdoor cap, cross-script chain key, flight flag) · `walks/styles.py` (diverse candidates,
status) · `walks/grounding.py` (rooftop, interactive claims) · `walks/constraints.py` (group 2–5) ·
`server.py` (`no_model` option) · `web/assets/app.js`, `i18n.js`, `i18n2.js`, `i18n3.js` (recovery
buttons, cancel, notices, styles reason, start message, map caption, group 2–5) · `eval/run_eval.py`,
`eval/queries.json` (simulated starts, outcome classes, styles expectation, timestamps, samples,
4 new scenarios) · `tests/test_v5.py`, `tests/test_planning.py`, `tests/e2e/*` (new regressions) ·
`docs/EVALUATION.md`, `docs/*`, `README.md`, `presentation/*` (numbers and counts).
