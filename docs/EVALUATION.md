# Evaluating Astana Walks as an AI system

Everything here is reproducible with `eval/run_eval.py`. **Only measurements that were actually run
are reported**, each with its dataset, model and denominator.

## The query set (`eval/queries.json`)

29 queries: 13 English, 9 Russian, 7 Kazakh. They cover:

| Area | Queries |
|---|---|
| Same request in three languages (paraphrases) | en01/ru01/kk01, en02/ru02/kk02, en05/ru05/kk05 |
| Negation ("no cafes", "только не кафе", "кафе керек емес", "кафесіз") | en02, ru02, kk02, en03, kk03 |
| Multi-intent and order ("coffee, then a walk") | en01, ru01, kk01, kk11 |
| Named places, aliases, spelling variants | en04, ru04, kk04 |
| Short windows, deadline + buffer + return | en06, ru06 |
| Family / group / slower pace | en07, ru07 |
| Bad weather / outdoor cap | en08, kk08 |
| Unsupported attributes (sockets, quietness), missing hours, wheelchair filter | en05, ru05, kk05, en09, ru09 |
| Impossible request, conflicting start, prompt injection | en10, ru10, en11 |
| Replacement, active-walk replan, plan styles | en12, ru12, en13 |

## Labels (documented, not invented)

* **Category labels** (`categories_any`): a candidate is relevant if its category fits the request.
  Hit@5 = at least one relevant place among the top 5 candidates. This measures retrieval *type*
  fit, not whether a specific place is good.
* `categories_none`: places of these categories anywhere in the candidates or plan are violations.
* `named`: the named place should be found by alias search and appear in the top 5 when it passes
  the hard filters (it may legitimately be too far for the time).
* `unknown`, `clarify`, `no_plan_ok`: see `label_rules` in the file.
* **POI-level labels**: we did not invent ground truth for real places. Each run writes
  `eval/results/<run>-to_label.csv` (top-5 per query). Fill `relevant` with 1/0 for your data
  snapshot, save as `eval/labels.csv`, and re-run: the summary then includes POI-level Hit@5 and
  precision@5.

## Metrics

| Metric | How |
|---|---|
| Hit@5 (category / named / POI) | from the trace's top-5 candidates |
| Hard-constraint violations | plan over budget or deadline cap, negated category, outdoor cap exceeded, closed at arrival |
| Unknown attributes reported | expected unsupported asks appear in "understood" |
| Clarification correct | conflicting start produces exactly one question |
| Empty results with suggestions | impossible requests explain and offer one-click changes |
| Names in all languages | every plan stop carries sourced names for kk/ru/en |
| Replacement / active walk / styles | others kept, return to the ORIGINAL start, remaining time respected, styles within budget |
| `--live` only: valid source-ID rate | accepted model items / (accepted + rejected) |
| `--live` only: malformed after repair, repair attempts | per query |
| `--live` only: removed unsupported claims, wrong-language warnings | automatic checks (limited, see below) |
| `--live` only: latency | first call (includes model loading) vs median of later calls |

## Results actually measured in the build environment

The build environment had **no real dataset** (OpenStreetMap was unreachable) and **no real model**.
So the only run here is a *pipeline check* on the **synthetic** E2E fixture (23 invented places)
**without a model** (a deterministic selector picks evidence P1–P3):

`eval/results/fixture-synthetic-lexical-nomodel.json` (fixed time: Wednesday 2026-10-21 14:30):

| Metric | Value | n |
|---|---|---|
| Hit@5, category labels | 0.625 | 24 queries with labels and a retrieval step |
| Hit@5, named place | 0.5 | 2 named places present in the fixture |
| Clarification correct | 1.0 | 1 |
| Unknown attributes reported | 1.0 | 3 |
| Plans with hard-constraint violations | 0 | 29 |
| Empty results that offered suggestions | 10 | 10 empty results |
| Plan stops with names in all three languages | 1.0 | 29 |

**What these numbers mean:** the fixture is tiny and laid out for UI tests (e.g. "Бәйтерек" is placed
4 km away from all other places), so many queries are honestly empty. These values check that the
code paths work; they say **nothing** about quality on real Astana data or about any model.
A `--live` run against the *fake* model was used only to check that the script works; its numbers
are not reported because a fake model always returns valid IDs.

## Results measured on the real dataset (your laptop, 2026-10-20)

Dataset: `data/pois.json`, 502 places (latest collection 2026-10-20 06:40 UTC), lexical retrieval,
model `qwen3:4b-instruct` via Ollama, `eval\run_eval.py --live`, fixed time Wednesday 14:30.
This run used **version 5.0** of the code (before the fixes listed below).

| Metric | Value | n |
|---|---|---|
| Hit@5, category labels | **0.87** | 23 |
| Hit@5, named place | 0.0 | 2 (see note 1) |
| Clarification correct | 0.5 | 2 (see note 2) |
| Unknown attributes reported | 1.0 | 3 |
| Plans with hard-constraint violations | **0** | 29 |
| Empty results that offered suggestions | 2 | 4 empty results (see note 3) |
| Plan stops with names in all three languages | 1.0 | 29 |
| Replacement kept the other stops, within budget | yes | 1 |
| Active-walk replan returned to the original start, within remaining time | yes | 1 |
| Plan styles offered | 0 | 1 (see note 4) |
| Model: valid source-ID rate | **1.0** | 33 model items |
| Model: malformed JSON after repair / repair attempts | 0 / 0 | 29 |
| Model: unsupported claims removed | 3 | 29 queries |

`scripts\doctor.py --infer` on the same laptop: two full requests took 6.5 s and 6.1 s; the model
call was 6.47 s / 6.14 s of that (retrieval 16.8 / 2.9 ms, planning 42.2 / 2.3 ms). The model was
already loaded, so "warm-up vs warm" shows almost no difference here. Naming audit: in English,
**95** of the 478 named places have a sourced name (`name:en` in OSM); **383** are shown with their
original name and an English type; 13 records had old guessed names demoted to search aliases.
Wikidata identity checks were not yet stored (re-run `scripts\enrich_wiki.py`).

What the run showed, and what version 5.1 changed (not yet re-measured on real data):

1. **Named places 0/2**: both named places (Baiterek, Khan Shatyr from Mega Silk Way, 120 min) are
   ≈ 4.5–5 km away — too far for a round trip at walking pace, so the hard filter correctly removed
   them, but the answer did not say so. 5.1 reports every named place that fails a filter with the
   reason and the estimated walk ("too far for your time, ≈ N min walk one way"), and the metric now
   counts Hit@5 only for reachable named places and "unreachable and explained" separately.
2. **Clarification 0.5**: one question was wrong or of the wrong kind. 5.1 drops weak location words
   ("у", "в", "at", "by"), ignores one-word prefix matches, and treats records with the same name
   within 600 m as one place; the label now accepts any single start question when one is expected.
3. **Two empty results without suggestions**: the model chose none of the candidates. 5.1 adds the
   one-click changes and the search-only list in that case too.
4. **No plan styles** for a one-stop plan: 5.1 also considers plans with up to three stops and shows
   a style only if it really beats the current plan on its own criterion.
5. Loading 502 places took 2.0 s (duplicate check compared all pairs); 5.1 compares only nearby
   records (500 synthetic places: 0.68 s → 0.005 s for that step).

## Second live run (your laptop, 2026-10-20, version 5.1) and version 5.2 fixes

504 places, lexical, `qwen3:4b-instruct`. Reported by you: category Hit@5 21/24 (0.875), valid
source IDs 33/33, no hard-constraint violations, replacement and active-walk replan passed.

| Finding | Root cause (established how) | Fix in 5.2 | Re-measured? |
|---|---|---|---|
| `kk03`, `kk11`: candidates retrieved, `error=timeout`, empty plan | The Ollama request had **no output-token cap** (`num_predict`) and the schema had no length limits, so a small model could keep generating until the 120 s timeout; Kazakh needs ~2× the tokens of English, and the evidence was pretty-printed JSON. Established by code inspection; the exact token count of your two calls was not recorded by 5.1. | `num_predict=700`, `maxLength` on every text field, compact evidence JSON trimmed to fit `num_ctx=6144`, a "keep texts short" line in the prompt; token counts and `done_reason` are now recorded in the trace and the eval report (`hit_output_cap`). On a model failure the page offers **Try again** and **Plan without AI text** (deterministic, same constraints, labelled "chosen by the app without the AI model"). | No (needs your Ollama) |
| `empty_results_with_suggestions` 3/5 | Model failures and "nothing feasible" were counted together. | Now `empty_no_feasible_place_with_suggestions` and `empty_because_model_failed` (with codes and query IDs) are separate. | Fixture only |
| `kk04` named place missed, `named_excluded={}` | **Retrieval defect**: "Хазірет Сұлтан мешітін" did not match "Хазрет Султан …" (spelling variant + Kazakh accusative "-ін"); reproduced on the 5.1 code with a synthetic record. | Multi-word sound-prefix matching across spellings, Kazakh case endings. `en04`/`ru04` distance exclusions unchanged. | Unit test only (the exact name of the mosque in your data is not known here) |
| `en13` styles count 0 | Styles were built from the top 8 of the pool, which can all be one type, so no "coffee + walk" alternative existed; same-chain names across scripts ("Кофе Бум"/"Coffee Boom") could also fill a plan. | Diverse candidate slice (≤3 per type, 12 total), chain check across scripts, explicit `styles_status` (`ok` / `no_other_feasible_plan` / `current_is_best`) shown in the page; the evaluator now requires ≥ 1 distinct alternative (`styles_min`). | Fixture: 2 alternatives |
| Start "(dataset centre…)" | **Evaluator only**: names like "EXPO" are not a place name in your data; the evaluator silently used the dataset centre. The app never substitutes a start (it asks for a place or a map point; the empty-start message was also fixed). | Documented SIMULATED coordinates for EXPO, Baiterek, Khan Shatyr, Mega Silk Way, marked "SIMULATED point" per row; unknown names now stop the run instead of guessing. | Fixture |
| `en08`, `kk08` category misses | "it's freezing, somewhere warm" contained no interest word, so the default "walk" categories were used and then removed by the 10-minute outdoor limit: a **ranking/understanding defect**. | New "somewhere warm indoors" interest (kk/ru/en words) and, with a tight outdoor limit and no stated interest, indoor types by default. | Unit test |
| `en09` category miss | Legitimate: the wheelchair filter (OSM tag yes/limited) left no museum. Not relaxed. | Reported as "not applicable: hard filter left no eligible place", with how many places of that type pass the filter anywhere in the data. | Fixture |
| `evaluated_at` 2026-10-21 | A fixed scenario clock (next Wednesday 14:30), not the run time. | Report shows `executed_at_astana_time` and `simulated_planning_time` separately; queries can set their own time (the late-night one uses 23:30). | Fixture |
| Name / language quality | `names_in_all_languages` only proves fields exist. | The report now lists, per stop, the names in kk/ru/en with their source kind and the AI text, for a human review. | Needs a human |

New queries added (none removed or relabelled to pass): `en14` tourist before a flight, `ru14` Mega Silk
Way 45 min, `en15` late-night/rooftop at 23:30, `kk15` child + interactive museum. One label changed with
evidence: `ru10` now expects "start" (either start question), because both question types ask once.

## What you should run on your laptop (and report)

```powershell
.venv\Scripts\python eval\run_eval.py                 # real data, no model: retrieval + constraints
.venv\Scripts\python eval\run_eval.py --live          # real data + your Ollama model
# optional, only if you installed requirements-semantic.txt:
.venv\Scripts\python eval\run_eval.py --mode both     # lexical vs hybrid on the same queries
```

Then put the actual numbers (with "n" and the dataset date) in the deck and in
`docs/TEST_SCENARIOS.md`. Do not claim the hybrid mode is better unless this comparison shows it
on your data; the default stays lexical.

## Limits of the automatic checks

* Claim checking (`walks/grounding.py`) recognises specific claim types in three languages (prices,
  free entry, ratings/popularity, sockets, quietness, crowds, events, Wi-Fi, wheelchair access,
  outdoor seating, "open now", years). It cannot catch every invented fact (e.g. a made-up history
  without a year). Unsupported sentences are removed before display and the card says so.
* The language check is script-based (Cyrillic vs Latin) and only flags clear mismatches.
* Category Hit@5 rewards type fit, not the best place; POI-level labels need a human.
* Kazakh quality of the model and of the optional embedding model is not assumed: review the
  Kazakh answers by hand (qualitative check) and say so in the presentation.
