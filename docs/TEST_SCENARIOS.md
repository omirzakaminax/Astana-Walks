# Test scenarios and limitations: Astana Walks

Three kinds of evidence are kept separate:

- **[AUTO-FIXTURE]** automated test on *synthetic* fixture data (`tests/fixtures/synthetic_pois.json`,
  labelled SYNTHETIC: not real places). Status: **179 tests, all passed** in the build environment
  (Python 3.13, `python -m unittest discover -s tests`, see `docs/test_run_log.txt`) on 2026-10-20.
- **[MOCK-LLM]** real HTTP round-trips against `server.py` or a *local mock* model server that
  returns fixed JSON. Tests plumbing and the API, not model quality. Status: passed.
- **[BROWSER]** the real web page in headless Chromium (`tests/e2e/browser_check.py`) against a
  SYNTHETIC dataset (`tests/e2e/e2e_pois.json`, contains deliberate duplicates, same-brand branches
  and Kazakh-only names) and a FAKE model (`tests/e2e/mock_ollama.py`): **69/69 checks passed** on
  2026-10-20, clicking the real controls. Map tiles, web fonts, photos and weather could not load
  there (no internet); Leaflet was replaced by a small stub so map-click logic could be checked.
- **[EVAL]** `eval/run_eval.py` on 29 KK/RU/EN queries; here only on the synthetic fixture without a
  model (pipeline check). See `docs/EVALUATION.md`.
- **[LIVE]** real OSM data + real Ollama model on your laptop. You collected 502 places (latest run
  2026-10-20, 21 linked to Wikidata, 14 photos); everything else live is still to do. Fill the
  "Observed (live)" column yourself.

## A. User scenarios (demo)

| # | Input (start, time, request) | Expected behaviour / type of answer | Evidence | Observed (fixture/mock) | Observed (live) |
|---|---|---|---|---|---|
| S1 | EXPO landmark · "I am near EXPO and have 45 minutes. Where can I walk?" | Budget parsed = 45 min (text wins over slider). 1–3 parks / viewpoints / public art reachable within 45 min round trip incl. minimum visit. Each card: source link, straight-line m, approx. walk min, visit min, hours status, AI "why" + AI activity. | AUTO-FIXTURE `test_short_walk_respects_budget`, `test_valid_output_is_grounded` | Near park (≈360 m) retrieved, 5 km park excluded as "too far for the time budget"; every candidate satisfies 2×walk ≤ 45. | *fill in* |
| S2 | Any start · "Хочу тихое место с кофе и розеткой недалеко" | Answer in Russian. Cafés only. Banner: «розетки, тишину» are not in our data — check on site. No claim of sockets/quiet in cards; if the model claims them, a warning appears. | AUTO-FIXTURE `test_coffee_with_unsupported_details`, `test_ungrounded_claim_warning` | Language = ru; top candidate is a café; `sockets` + `quiet` flagged; generated text "quiet place with power sockets, rating 4.9" got the warning "…NOT confirmed by our data". | *fill in* |
| S3 | Any start · "I am with a child and have one hour" | Playgrounds / parks / museums / ice cream within 60 min. Museums closed now per OSM hours are excluded and counted in the trace. | AUTO-FIXTURE `test_family_and_closed_museum` | Monday 14:00: playground included, museum with "Tu-Su 10:00-18:00; Mo off" excluded ("closed now according to OSM hours"); on Tuesday it is included. | *fill in* |
| S4 | Any start · "Я турист, у меня 2 часа: что посмотреть рядом?" | Sights/museums/viewpoints, budget 120 min, mini-route block with total time and "fits / does not fit". | AUTO-FIXTURE `test_parse_minutes`, `test_mini_route` | "у меня 2 часа" → 120; route with 2 places has 3 legs (start→A→B→start). | *fill in* |
| S5 | Kazakh UI · "Баламен бірге бір сағатымыз бар" | Language kk, intent "with kids", 60 min; the model is told to answer in Kazakh; category labels in the evidence are Kazakh; a note warns that Kazakh AI text may contain mistakes. | AUTO-FIXTURE `test_kazakh_intents_and_time`, `test_answer_language_is_passed_to_model`; BROWSER | as expected | *fill in* |
| S6 | Harsh weather (e.g. −20 °C feels-like) · "a walk or a coffee" | Weather tag "rough weather: indoor places first"; cafés ranked above parks; nothing excluded because of weather. | AUTO-FIXTURE `test_harsh_weather_boosts_indoor`, `test_weather_parsing` | indoor bonus applied only in harsh weather | *fill in* |

## B. Edge and failure cases

| # | Case | Expected | Evidence | Observed |
|---|---|---|---|---|
| E1 | Opening hours missing | Card: "Opening hours not listed in the source — check before going". Place kept. | AUTO-FIXTURE `test_open_closed_unknown`, `test_labels_never_claim_certainty` | as expected |
| E2 | Opening hours in unsupported format (`Mo-Fr 08:00-20:00; PH off`) | Raw text shown, "current status not verified". Place kept. | AUTO-FIXTURE `test_unknown_hours_are_kept_but_flagged` | status = unknown, kept |
| E3 | Overnight hours (`18:00-04:00`) | Open at 02:00, closed at 14:00. | AUTO-FIXTURE `test_overnight` | as expected |
| E4 | No suitable places (museum, 10 min) | Honest "No places in our dataset fit…" message; **LLM is not called**. | AUTO-FIXTURE `test_no_matches`, `test_no_candidates_skips_llm` | as expected |
| E5 | Invalid coordinates (`abc`, `95, 71`, Almaty `43.2, 76.9`) | Clear validation message, no request made. | AUTO-FIXTURE `test_invalid_coordinates`; MOCK-LLM headless UI run | UI showed "This prototype only covers Astana…" |
| E6 | Empty request and no interests | "Please type what you would like to do or pick at least one interest." | AUTO-FIXTURE `test_empty_input`; headless UI run | as expected |
| E7 | Collection failure (timeouts on all mirrors) | Script tries each mirror with back-off, then exits with a clear message; existing `data/pois.json` unchanged. | AUTO-FIXTURE `test_fetch_retries_then_fails_cleanly`, `test_failed_collection_keeps_existing_file` | 4 attempts (2 mirrors × 2), file unchanged |
| E8 | LLM down (Ollama not running) | Red error "Cannot reach Ollama… Open the Ollama app or run `ollama serve`" + list of retrieved places labelled "Search results only — not AI recommendations". | AUTO-FIXTURE `test_llm_failure_is_reported`, MOCK-LLM `test_ollama_down_message`, headless UI run | as expected |
| E9 | Model not installed | "Run: ollama pull qwen2.5:1.5b" | MOCK-LLM `test_missing_model_message` | as expected |
| E10 | Model returns non-JSON / JSON inside text | Non-JSON → clear error; JSON wrapped in prose → extracted. | AUTO-FIXTURE `test_malformed_json`, `test_json_wrapped_in_text` | as expected |
| E11 | Model invents an ID / duplicates / out-of-range time | Unknown IDs and duplicates rejected and listed in the trace; visit time clamped; every shown POI ID exists in the dataset. | AUTO-FIXTURE `test_valid_output_is_grounded`, `test_real_ids_also_accepted` | 3 of 4 items rejected; visit 999 → clamped |
| E12 | User coordinates sent to the model? | Never — only distances. | AUTO-FIXTURE assertion in `test_valid_output_is_grounded` | coordinates absent from prompt |
| E13 | Missing dataset | App shows "No dataset yet" + the collector command and stops. | Headless UI run | as expected |
| E14 | Gemini selected without key | Clear message to set `GEMINI_API_KEY`/`GEMINI_MODEL` or switch to Ollama. | MOCK-LLM `test_gemini_without_key` | as expected |
| E15 | Start point recommended to itself | The landmark you start from is never suggested. | MOCK-LLM `test_recommend_landmark` | excluded |
| E16 | Weather service unreachable | App works without the weather tag; no error shown. | AUTO-FIXTURE `test_weather_failure_returns_none` | as expected |
| E17 | Error messages in the chosen language | Server returns error codes; the page shows them in kk/ru/en. | MOCK-LLM `test_llm_error_code_reaches_client`, `test_recommend_coords_and_errors` | codes `ollama_unreachable`, `outside_astana`, `bad_coords`, `empty_request`, `bad_request` |
| E18 | Path traversal (`/assets/../server.py`) | 404, no file served. | MOCK-LLM `test_index_and_assets` | 404 |
| E19 | Geolocation denied | Message "Location access was denied. Pick a place from the list instead." | Manual check on your laptop | *fill in* |

**Browser check:** the page was opened in headless Chromium (Kazakh dark, Russian light, English
low-vision, Russian at 390 px phone width). Findings fixed during the check: native number
spinners duplicated the custom ▲▼ buttons; long place names were cut off; the start place could
be recommended to itself; Kazakh weekday names were missing in the browser's date library; the
low-vision mode did not enlarge rem-based text. **The map with real tiles and the web fonts have
not been seen yet: check them on your laptop.**

## C. Live checks you must run (and record results here)

1. `scripts\collect_osm.py` → real place count: ____ ; categories: ____
2. `scripts\check_llm.py` → model answered: yes/no ; time: ____ s ; all IDs valid: yes/no
3. App, scenarios S1–S4 on real data → note the places returned and any warnings.
4. Stop Ollama and run one request → E8 message appears.

## D. Limitations

- Data = OpenStreetMap: three collected areas plus a citywide sights pass; coverage and hours can be
  incomplete or outdated; no ratings, prices or events. "Collected on" is the download date, not a
  verification date.
- Many places have no sourced English name; the English page then shows the original name with an
  English type (and, for simple cases, a labelled descriptive translation). Reviewed overrides are
  possible but none are shipped.
- Distances are straight-line; walking time = distance × 1.3 ÷ 75 m/min, labelled approximate.
- Visit durations are our heuristic ranges per category, labelled approximate.
- Opening-hours parser handles common formats; others shown raw as unverified. Public holidays
  are not considered.
- Intent detection is keyword-based in Kazakh, Russian and English; unusual phrasings fall back to
  "general walk" (shown to the user as assumed).
- Kazakh interface texts were written without a native-speaker review; Kazakh AI answers from a
  4B model can contain grammar mistakes (the interface says so).
- Weather is for the dataset area (near EXPO), not the user's exact location, and only re-ranks;
  it never excludes places.
- A small local model can produce weak or invalid answers; the app rejects invalid ones but cannot
  guarantee eloquent explanations. Speed depends on the laptop.
- Route order: every order of up to 3 stops is checked on straight-line estimates, not real streets.
- Walking directions are handed to Google Maps / OpenStreetMap on click; their route and time can
  differ from the in-app estimate.
- Accessibility filter uses only the OSM `wheelchair` tag of the place; the route is not checked.


## F. Version 3 features (actual results, 2026-10-19)

Automated suite: `python -m unittest discover -s tests` → **113 tests, all passed** (log:
`docs/test_run_log.txt`). Browser check: **41/41 passed**. All with synthetic data, a fixed or
real clock, and a fake model. Nothing here proves real-world availability or real-model quality.

| Journey | Test(s) | Result |
|---|---|---|
| Cards, timeline, map numbers and export use one plan; total = all legs + displayed visits | `test_total_includes_all_legs_and_displayed_visits`, `test_cards_plan_and_route_agree`, `test_plan_is_canonical_in_response`, browser "timeline stops == cards", JS export tests | passed |
| Old bug: route summed minimum visits while cards showed longer ones | fixed; same tests assert `total == sum(legs) + sum(card visits)` | passed |
| Multi-stop plan over budget is shortened (never below minimum) then reduced, with notes | `test_over_budget_plan_is_shortened_then_reduced`, `test_infeasible_is_never_reported_as_fitting` | passed |
| Back-by: 14:30, 15:30, buffer 10 → 50 min; 15:25 → "buffer exceeds time left"; past time; explicit next day; >24 h; bad buffer | `test_deadline_acceptance_example`, `test_past_and_next_day_deadlines`, `test_deadline_errors` (API), browser "past deadline" | passed |
| "I have two hours" cannot exceed a nearer deadline | `test_text_cannot_exceed_deadline`, `test_deadline_caps_text_duration` | passed |
| Slower pace changes feasibility; concurrent requests keep their own pace | `test_pace_changes_feasibility`, `test_concurrent_requests_do_not_share_pace`, `test_pace_is_request_scoped` | passed |
| Group: shortest time + slowest pace; conflicting interests covered or limitation shown; back to solo without stale settings | `test_group_uses_min_time_and_slowest_pace`, `test_group_coverage_and_compromise`, `test_group_limitation_is_reported`, `test_group_min_time_slowest_pace_and_coverage`, browser group/solo checks | passed |
| Outdoor cap enforced while building (walking + outdoor visits; strict mode; OSM-tag vs estimate); works without weather | `test_outdoor_cap_counts_walking_and_outdoor_visits`, `test_outdoor_cap_without_weather`, `test_outdoor_cap_is_hard_and_not_relaxed` | passed |
| Opening hours at arrival (opens after "now", closes during the visit) | `test_hours_checked_at_arrival`, `test_arrival_hours_exclude_closing_place` | passed |
| Replace one place, others and their durations kept; closed report; too far → closer; LLM failure keeps plan with labelled app reasons | `test_replace_keeps_other_stops`, `test_replace_too_far_picks_closer`, `test_replace_llm_failure_keeps_plan_with_calc_text`, `test_replace_flow`, browser replace/closed/remove | passed |
| No feasible replacement; exclusions never reintroduced | `test_replace_respects_exclusions_and_reports_none` | passed |
| Surprise without text; varied types; avoids previous plan; respects visited; exhausted / none; LLM failure labelled | `test_surprise_without_text_and_variety`, `test_surprise_respects_visited_and_exhaustion`, `test_surprise_llm_failure_is_labelled`, `test_surprise_api`, browser surprise checks | passed |
| Copy/save: escaping, only http(s) links, no coordinates unless opted in, no scripts/external files, all 3 languages | `tests/js/plan_test.js` (via `test_plan_js`), browser copy/save checks | passed |
| Bingo: completion, progress, replacement does not transfer completion | JS "bingo tasks and replacement invalidation", browser bingo check | passed |
| Invalid API input → structured codes; old request format still works | `test_invalid_inputs_are_structured`, `test_replace_invalid_inputs`, `test_invalid_values_rejected`, `test_old_request_format_still_works` | passed |
| Duplicates (Мега Силк Вей / Mega Silk Way, Хан Шатыр / Khan Shatyr) merged; numbered names kept apart *(v5: the "all Latin" English rule was replaced by sourced names, see section G)* | `test_cross_script_duplicates_merged`, `test_fixture_loader_merges_duplicates_on_load`, `test_numbered_names_are_not_merged`, browser "no duplicates", "English: every start option in Latin script" | passed |
| Citywide notable landmarks query and flag; "must-see" boost | `test_landmarks_query_and_notable_flag`, `test_must_see_boosts_notable` | passed (query not run against real Overpass) |
| Photos + descriptions: licence required, author HTML stripped, unsafe links rejected, Wikipedia → Wikidata fallback, batched polite requests, failure leaves the file unchanged, synthetic data refused | `tests/test_enrich.py` (mocked Wikidata/Commons/Wikipedia responses) | passed (real services not reached from the build environment) |
| Cards show photo with licence credit and description with source badge; HTML in descriptions not rendered; failed image hidden | browser checks "about: …", "photo: …"; screenshot with a stand-in image | passed |
| Photos and descriptions: Wikidata/Commons/Wikipedia parsing, licence required, non-free skipped, unsafe links dropped, HTML stripped, failure leaves the file unchanged, synthetic file refused | `tests/test_enrich.py` (mocked HTTP shaped like the real APIs) | passed (real Wikimedia services not reached from the build environment) |
| Photo card: credit with author + licence + Commons link; description with source badge; image that fails to load is hidden; "Кофе Бум" → "Coffee Boom" | browser checks + screenshots (stand-in image served for the Wikimedia address) | passed |
| 3 languages, dark, low-vision, phone width: no raw keys, no horizontal scroll, no JS errors | browser checks 02–04 + screenshots inspected | passed |

Found and fixed during this round: names differing only by a number were merged ("cafe 10" /
"cafe 11"); the custom outdoor field showed while a preset was selected; the "shortened" note did
not say why; the first card fact was mislabelled; the route text described the old ordering.

### Still to verify on your laptop (cannot be done here)

1. `collect_osm.py --all` against the real Overpass API: count, notable count, duplicates gone;
   and its final enrichment step against the real Wikidata/Commons/Wikipedia (photos and descriptions appear on cards).
2. A real Ollama model answering through `check_llm.py` and the page (speed, JSON validity,
   Kazakh quality).
3. The map with real tiles and the web fonts.
4. Real geolocation permission prompt and denial message.
5. Clipboard and download behaviour in your own browser (Chrome/Edge on Windows).
6. Read aloud voices on Windows (Kazakh may fall back to Russian).


## G. Version 5 journeys (actual results, 2026-10-20)

Automated: **179 unit/API tests passed** (`tests/test_v5.py` adds 53); **plan.js 12/12** (Node);
**browser 69/69** (synthetic data, FAKE model, Leaflet stub). Evaluation: fixture-only pipeline
check (`docs/EVALUATION.md`). Nothing here proves real-data quality or real-model behaviour.

| Journey | Test(s) | Result |
|---|---|---|
| Explicit English name wins; Kazakh-only name stays original with an English type, descriptive translation and pronunciation aid only as labels; Kazakh Cyrillic not called Russian; dative monument name untouched; Latin brand untranslated | `NamePolicyTests` | passed |
| Old guessed names (from the alphabet or unchecked Wikidata) demoted to unverified aliases on load; file not modified | `test_legacy_guessed_names_become_unverified_aliases`, `test_labels_are_stored_with_identity_never_as_osm_names` | passed |
| Wikidata label used only after identity check; namesake (person) and far items rejected | `test_wikidata_label_only_with_identity_ok`, `test_identity_check_rejects_namesake_and_far_items` | passed |
| Overrides need a source URL and review date | `test_overrides_need_source_and_review_date` | passed |
| API sends names for all three languages; language switch updates picker, cards, route and export identically without a model call | `test_api_returns_all_languages_for_instant_switching`; browser "language switch …" (2 checks) | passed |
| Same-brand branches, different house numbers, park vs attraction never merged; real merges keep reason + alias | `DedupTests`; `test_branches_of_one_brand_not_offered_together` | passed |
| Search: Latin spelling, Cyrillic, Kazakh letters, case ending ("Байтерека"), initials ("AITU"), descriptive alias, no-match message | `SearchTests`; browser picker checks (8) | passed |
| Negation in kk/ru/en is a hard filter; "then" keeps the asked order; multi-intent plan covers both | `QueryUnderstandingTests` | passed |
| Start named in text far from the selected start → one question; "keep" plans from the selected start | `test_start_conflict_asks_once`; browser "clarify" (2) | passed |
| Named destination included when feasible | `test_named_destination_is_included_when_feasible` | passed |
| "Free entry and a quiet cafe. Sockets are unknown." → free entry and quietness removed, honest part kept | `test_honest_unknown_does_not_excuse_other_claims`, `test_unsupported_sentences_removed_before_display` | passed |
| Claims checked against specific evidence fields (Wi-Fi tag, fee=no), not words in the JSON; years and "open now" | `test_supported_by_specific_fields_only`, `test_open_now_and_invented_years` | passed |
| JSON Schema with allowed IDs sent; fallback to "json" on old Ollama; one repair then transparent failure | `ModelContractTests`, `OllamaClientTests` | passed |
| Plan styles within the same budget/outdoor cap, no duplicates; switching explains only new stops | `test_styles_satisfy_the_same_constraints`, `test_style_switch_explains_only_new_stops`; browser styles (2) | passed |
| Active walk returns to the ORIGINAL start; remaining time; deadline recomputed from now | `ItineraryAnchorTests`, `test_active_walk_*`; browser walk (3) | passed |
| Empty result: reasons + one-click changes; deadline never offered as droppable | `test_empty_result_suggestions_never_drop_deadline`; browser "no plan" | passed |
| Source filters validated; known-hours filter applied | `test_filters_validated_and_reported`, `test_filters_known_hours_and_wheelchair` | passed |
| Directions: Google `api=1` + `travelmode=walking` + waypoints; private start only with consent; OSM foot routing one leg | `tests/js/plan_test.js` "directions links"; browser directions (3) | passed |
| Report a problem: local, downloadable JSON without coordinates or query, deletable | browser report (3) | passed |
| Invalid records skipped with reasons; backup before save; audit counts | `DataPipelineTests` | passed |
| Hybrid retrieval: RRF after hard filters (FAKE encoder); explicit lexical fallback when not installed | `SemanticFusionTests` | passed (real embedding model NOT run) |
| Fit facts and timings in the response | `test_fit_facts_and_timings` | passed |

### Measured on your laptop (2026-10-20, version 5.0)

`data_report.py`: 502 places; English names: 95 from OSM `name:en`, 383 original + type; 13 legacy
names demoted. `doctor.py --infer`: 13 OK/WARN, 0 FAIL; two model requests 6.5 s / 6.1 s.
`run_eval.py --live`: category Hit@5 0.87 (n = 23), 0 hard-constraint violations (n = 29), valid
source IDs 1.0 (33 items), 0 malformed. Details and the fixes made afterwards: `docs/EVALUATION.md`.

### Still to verify on your laptop (version 5)

1. `scripts\data_report.py` on your real `data\pois.json` → actual name/coverage counts.
2. `scripts\collect_osm.py --all` + `scripts\enrich_wiki.py` with the new code (backup, identity checks).
3. `scripts\doctor.py --infer` and `eval\run_eval.py --live` with your real Ollama model.
4. Optional: `eval\run_eval.py --mode both` after installing `requirements-semantic.txt`.
5. Map-start click on real tiles, directions links on a phone, real geolocation for "I'm here".
6. A Kazakh speaker reading the Kazakh texts (interface and AI answers).

## Version 6: Discover (Place of the day, gallery, quiz)

| Scenario | How checked | Status |
|---|---|---|
| `/api/gallery` lists only places with a licensed, non-generated photo; daily pick is stable for a date | `test_gallery_only_licensed_photos_and_a_stable_daily_pick` | passed |
| Place-of-the-day card shows licence credit and the note "a daily pick, not a ranking" | browser check "discover: place of the day…" | passed |
| Gallery tile opens an accessible dialog (name, type, description with source, credit); Esc closes it | browser checks | passed |
| Guess mode hides names on tiles and in image alt text; 3 options; verdict in words; score updates | browser checks | passed |
| "Start my walk here" from the dialog sets the start point | browser check | passed |
| Photo that cannot load shows a labelled offline placeholder, not a broken image | screenshot inspected | passed |

All on synthetic data with a stand-in image; real photos come from the user's `enrich_wiki.py` run (Wikimedia Commons).
