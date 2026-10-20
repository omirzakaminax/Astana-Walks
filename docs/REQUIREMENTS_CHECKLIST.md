# Requirements → implementation checklist

Source of truth: hackathon PDF, Case 1 (НИЦ Smart City). ✅ done in code/docs · 🟡 done but must be
verified/run by you · ⬜ your action.

## Deliverables («Что ожидается от команд»)

| # | Requirement | Where | Status |
|---|---|---|---|
| 1 | Product concept: idea, audience, use cases | `docs/CONCEPT.md`, slides 1–2 | ✅ |
| 2 | Demo / prototype on several scenarios (real or simulated locations) | `server.py` + `web/` (local web app); landmark = simulated location, plus typed coordinates and browser geolocation | 🟡 run on real data |
| 3 | High-level RAG description | `docs/CONCEPT.md` §RAG, slide 3, in-app "How this answer was built" | ✅ |
| 4 | Test scenarios with inputs + expected answer type | `docs/TEST_SCENARIOS.md` | ✅ (live column ⬜) |
| 5 | 5–7 min presentation: business idea, limitations, risks, plan | `presentation/Astana_Walks_pitch.pdf/.pptx` + notes | ✅ (update the real POI count ⬜) |
| 6 | Ethics & privacy notes | `docs/CONCEPT.md` §Ethics, slide 5, sidebar | ✅ |

## Data

| Requirement | Where | Status |
|---|---|---|
| Name, coordinates, short description, category/tags, hours/contacts if present | `walks/osm_collect.py` → `data/pois.json` | ✅ code · ⬜ run collector |
| Rating/popularity "if available" | Not available in OSM → explicitly "not in our data" | ✅ honest gap |
| Dataset collected by the team, collection automated | `scripts/collect_osm.py` (Overpass, mirrors, back-off, dedup, validation, atomic save) | ✅ code · ⬜ run |

## Expected output per scenario

| Requirement | Where | Status |
|---|---|---|
| 1–3 concrete places | `pipeline.validate_output` caps at 3 | ✅ |
| Short "why" | model `why`, labelled AI-generated | ✅ |
| Approximate visit time | clamped `visit_minutes` + category range | ✅ |
| "What to do there" | model `activity`, labelled AI suggestion; mini-route | ✅ |

## Constraints («Ограничения и требования»)

| Requirement | Where | Status |
|---|---|---|
| Clearly state which data is used (location, filters, tags) | "Understood:" line, trace expander, sidebar | ✅ |
| No confident "open now" without data; show certainty | `walks/hours.py` labels; risky-claim warnings | ✅ |
| Label source data vs generated idea | green "Source data" / purple "AI-generated" badges | ✅ |

## Judging criteria → traceability (criterion → behaviour → evidence → test → limitation)

| Criterion (brief's order) | Implemented behaviour | Evidence / demo scenario | Tests | Remaining limitation |
|---|---|---|---|---|
| 1. Relevance and usefulness | Hard filters in code (time, distance, type, "no …", hours at arrival, outdoor cap, source filters); BM25 + type fit + proximity; named places as destinations; multi-intent coverage; one place per chain; plan styles | Demo S1 "coffee then a short walk, no museums"; S2 "I want to see Baiterek" | `test_v5` QueryUnderstanding/ApiV5, `test_core`, `test_planning`; `eval/run_eval.py` category Hit@5 (fixture only so far) | Real-data Hit@5 and POI-level labels must be run on the laptop; no ratings/popularity in OSM |
| 2. Context and adaptability | Pace, deadline + buffer, group (2–5), weather, outdoor cap, active-walk replan from the current position with the original return point, start-conflict clarification | Demo S3 "back by 15:30 + 10 min outdoors"; S5 "I'm here" | `test_api_features`, `ItineraryAnchorTests`, `test_active_walk_*` | Straight-line × 1.3 walking estimate, not a street route |
| 3. Explanation quality | Model "why"/"what to do" grounded clause by clause; unsupported sentences removed; calculated "How it fits" list; source vs AI vs calculated badges; trace with evidence, timings and retrieval mode | Any card; "How this answer was built" | `GroundingTests` (incl. "Free entry and a quiet cafe. Sockets are unknown."), `ModelContractTests` | Automatic checks cover listed claim types only; Kazakh text quality needs a human review |
| 4. UX and demo clarity | Searchable picker, map start, sentence builder, one canonical plan, styles, directions hand-off, empty-result help with previews, KK/RU/EN, themes, low-vision mode, read aloud, phone layout | Demo script `docs/DEMO_SCRIPT.md` | Browser check: 69/69 on synthetic data with a fake model (KK dark, EN low-vision, RU phone) | Real tiles, real geolocation and voices only checkable on the laptop |
| 5. Creativity / distinctive features | Plan styles, "I'm here" walk, Surprise me, City Bingo, "don't let me freeze", go together, offline export, report a problem, provenance-aware names, Place of the day, "Astana in photos" gallery with a Guess-the-place quiz, skyline + qoshqar-muiz visual identity | Demo S4 styles + S5 walk | `test_v5` ApiV5, browser checks | — |
| 6. Ethics and privacy | Local model by default; coordinates never sent to the model or logged; no accounts/history; directions only on click, private start only with consent; reports local and without coordinates; licences shown; no AI venue photos; unknown ≠ no for accessibility | Footer, export checkbox, directions note | `test_server_i18n` (no coordinates to model), report download check | Map tiles/photos load from OSM/Wikimedia servers (they see the IP) |
| 7. Completeness | Collector + enrichment + audit, tests, evaluation set, diagnostics, docs, deck, demo script | `README.md`, `docs/`, `eval/`, `presentation/` | 179 unit/API tests + 77 browser checks (this build) | Real dataset counts, real-model metrics and the YouTube video are produced on your laptop |

## Submission format

See `docs/SUBMISSION_CHECKLIST.md`.

## Not implemented / partial (honest)

- Real walking routes (straight-line estimate only).
- Ratings/popularity, live events, prices — not in the data source.
- Kazakh: implemented (interface, request understanding, AI answers), but texts not reviewed by a native speaker.
- Group planning: implemented as one shared walk for 2–5 people (no rooms, invitations or multiple starting points).
- Accessibility: only shows the OSM `wheelchair` tag where present; no dedicated filter.

## Version 3 upgrade (eight features)

| Feature | Implemented | Tests run | Manual check left |
|---|---|---|---|
| Canonical itinerary + route timing fix | ✅ `walks/itinerary.py` | unit + API + browser | real data |
| 1. Back by… (deadline + buffer) | ✅ | unit + API + browser | real clock on your laptop |
| 2. Replace / visited / closed / too far / remove | ✅ | unit + API + browser | real data |
| 3. Don't let me freeze (outdoor limit) | ✅ | unit + API | real weather |
| 4. Surprise me | ✅ | unit + API + browser | real data |
| 5. Copy / save / share plan | ✅ | JS (Node) + browser | your browser's clipboard/download |
| 6. Go together (2–5 people) | ✅ | unit + API + browser | — |
| 7. Walking pace | ✅ | unit + API (concurrency) + browser | — |
| 8. City Bingo / walk passport | ✅ | JS (Node) + browser | — |
| Duplicates merged; names in chosen language; citywide must-see collection | ✅ | unit + browser | `collect_osm.py --all` against real Overpass |


## Version 5 (final improvements) — status

| Improvement | Implemented | Tests actually run here | Manual verification left (your laptop) |
|---|---|---|---|
| Provenance-aware names, migration, overrides, audit | ✅ `walks/names.py`, `data.py`, `report.py` | unit (NamePolicy, Dedup, DataPipeline) + browser (EN picker, language switch agreement) | run `scripts\data_report.py` on real data; add sourced overrides if you can verify them |
| Conservative dedup with reasons | ✅ `walks/dedup.py` | unit (branches, park vs attraction, node+area) | check `merges_by_reason` in the report |
| Wikidata identity check + cache | ✅ `walks/enrich.py` | unit (identity_check) | re-run `scripts\enrich_wiki.py` against real Wikimedia |
| Negation, sequence, named places, start conflict | ✅ `text.py`, `search.py`, `server.py` | unit + API + browser | try the demo phrases on real data |
| Hybrid retrieval (optional) | ✅ `semantic.py` | unit with a FAKE encoder; fallback when not installed | install, run `eval\run_eval.py --mode both`; keep lexical unless it measurably helps |
| Clause-level grounding + removal | ✅ `grounding.py` | unit (incl. required regression) | read real model answers; Kazakh review |
| Structured output + 1 repair | ✅ `llm.py`, `pipeline.py` | unit (schema passed, fallback to "json", bounded repair) | `scripts\doctor.py --infer` with your Ollama version |
| Searchable picker + map start | ✅ | browser (keyboard, case ending, no-match, map click with a Leaflet STUB) | real map tiles and touch on a phone |
| Plan styles | ✅ `styles.py` | API + browser | real data variety |
| Walking directions hand-off | ✅ `plan.js` | Node + browser (URL shape) | open the links on a phone |
| "I'm here" active walk | ✅ | API + browser (return to the original start) | real geolocation permission flow |
| Empty-result help + source filters | ✅ | API + browser | — |
| Report a problem | ✅ | browser (save, download without coordinates, delete) | — |
| Diagnostics, latency, evaluation | ✅ `doctor.py`, `eval/run_eval.py` | ran on SYNTHETIC data with no/fake model only | run both on real data with the real model and copy the numbers |
