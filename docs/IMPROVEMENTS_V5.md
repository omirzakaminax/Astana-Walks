# Version 5: audit, changes and verification status

## 1. Audit of the previous version (reproduced, not assumed)

Baseline before changes: `python -m unittest discover -s tests` → 113 passed; `plan.js` tests → 11 passed
(Python 3.13, build environment; `pytest` itself is not installed there, `unittest` was used).

| Review observation | Reproduced on the previous code | Result |
|---|---|---|
| `walks/data.py display_name()` English fallback calls `to_latin()` | `display_name({"name": "Атырау көпірі"}, "en")` → `("Atyrau kopiri", True)` | confirmed → replaced by `walks/names.py` |
| `web/assets/plan.js displayName()` repeats its own transliteration | same map + KNOWN words in JS | confirmed → removed; the page renders API names |
| `walks/dedup.py` stores the second name as `ru` if Cyrillic, else `en` | merging "Mega Silk Way" + "Мега Силк Вей" stored `names.ru = "Мега Силк Вей"` (could be Kazakh) | confirmed → merged names become aliases with their source element |
| `walks/enrich.py` fills missing names from Wikidata labels without provenance | code path `p["names"].setdefault(lang, label)` | confirmed → labels stored in `media.labels` with an identity check |
| `pipeline.ungrounded_claims()` returns nothing if "unknown" appears anywhere | `ungrounded_claims("Free entry and a quiet cafe. Sockets are unknown.", …)` → `[]` | confirmed → clause-level `walks/grounding.py`; regression test added |
| The uploaded ZIP had no real `data/pois.json` | by design (data stays on your laptop; you reported 502 places) | confirmed → migration happens on load; nothing in the ZIP overwrites your data |

## 2. Final table

Evidence kinds: **F** = automated test on synthetic fixtures with a fake model; **B** = browser check on
synthetic data with a fake model; **E** = evaluation script on the synthetic fixture without a model;
**R** = real data / real model — *not available in the build environment, nothing claimed*.

| Improvement | Implemented | Evidence / tests actually run | Remaining manual verification |
|---|---|---|---|
| Provenance-aware names (override → OSM `name:xx` → checked Wikidata label → OSM Latin name → original + type; translit only as alias/aid) | yes | F: `NamePolicyTests` (10); B: EN picker, language-switch agreement across picker/cards/route/export | R: run `scripts\data_report.py` on your 502 places; read the English page |
| Conservative migration of legacy names | yes (in memory on load; collector writes after a backup) | F: `test_legacy_guessed_names_become_unverified_aliases` | R: check "legacy names demoted" in the report |
| Reviewed overrides file | yes, **empty** (IDs/sources not verifiable here) | F: `test_overrides_need_source_and_review_date` | add entries only after checking IDs and sources |
| Naming + data-quality audit | yes (`scripts/data_report.py`) | F: `test_report_counts`; ran on the synthetic E2E fixture | R: run on real data |
| Conservative dedup with reasons | yes | F: `DedupTests` (4), API "one place per chain" | R: inspect `merges_by_reason` |
| Validation (IDs, URLs, coordinates, text, schema version) + backups + Wikimedia cache + identity check | yes | F: `DataPipelineTests`, `test_identity_check_rejects_namesake_and_far_items`, existing enrich tests | R: re-run `collect_osm.py --all` and `enrich_wiki.py` |
| Negations, sequence, named places, start clarification | yes | F: `QueryUnderstandingTests`, `SearchTests`, API clarify/named; B: clarify (2) | R: try the demo phrases on real data |
| Source filters (known hours, OSM wheelchair) | yes | F + B | — |
| Optional hybrid retrieval (multilingual-e5-small, RRF) | yes, off by default | F: FAKE encoder + fallback test. **Real model not installed or run** | R: install and run `eval\run_eval.py --mode both` |
| Clause-level grounding, removal before display | yes | F: `GroundingTests` (7) incl. the required regression | R: read real answers; Kazakh review |
| JSON Schema output, temperature 0.1, ≤1 repair, transparent failure | yes | F: `ModelContractTests` (4), `OllamaClientTests` | R: `doctor.py --infer` with your Ollama version |
| Concrete "How it fits" (calculated) | yes | F: `test_fit_facts_and_timings`; B: cards | — |
| Searchable picker + map start | yes | B: 12 picker/map checks (map via a Leaflet stub) | R: real tiles, touch on a phone |
| Plan styles | yes | F: 2 API tests; B: 2 | R: variety on real data |
| Walking-directions hand-off | yes | F (Node): URL shapes, consent; B: 3 | R: open the links on a phone |
| "I'm here" active walk | yes | F: anchor + remaining time + deadline; B: 3 | R: real geolocation flow |
| Empty-result explanations + one-click changes | yes | F: suggestions never drop deadline; B: 1 | — |
| Report a name/data problem (local) | yes | B: save, download (no coordinates/query), delete | — |
| Performance and robustness (cached BM25 and search index, bounded model concurrency, stale-response guard) | yes | F/B suites; mention detection measured at ≈0.2 s on 600 synthetic places with a long request | R: `doctor.py --infer` timings on your laptop |
| Diagnostics (`scripts/doctor.py`) | yes | ran against the synthetic fixture and the fake model | R: run on the laptop |
| Evaluation (29 KK/RU/EN queries, documented labels) | yes | E: `eval/results/fixture-synthetic-lexical-nomodel.*` (pipeline check only) | R: `eval\run_eval.py` and `--live`; optional POI labels |
| Docs, deck, demo script | updated | deck rendered and inspected (10 slides) | replace `[ ]`/`<N>` placeholders with your measured numbers |

Totals in this build: **179 unit/API tests passed**, **plan.js 12/12**, **77/77 browser checks**
(see `docs/test_run_log.txt`). None of these used real places or a real model.
