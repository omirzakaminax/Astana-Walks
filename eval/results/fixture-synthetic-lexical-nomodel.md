# Evaluation: fixture-synthetic-lexical-nomodel

Measured by eval/run_eval.py. Nothing here is estimated.

* dataset: tests/e2e/e2e_pois.json
* dataset_kind: synthetic
* places: 23
* dataset_collected_at: 2026-10-19T00:00:00+00:00
* executed_at_astana_time: 2026-10-20 21:02
* simulated_planning_time: 2026-10-21 14:30 (Wednesday) — fixed scenario clock (use --now to change)
* retrieval_mode_requested: lexical
* retrieval_mode_used: ['lexical']
* model: NO MODEL (deterministic selector)
* labels: category-level (eval/queries.json label_rules)

## Summary

```json
{
 "queries": 33,
 "hit_at_5_category": {
  "value": 0.731,
  "n": 26
 },
 "hit_at_5_named_place": {
  "value": 1.0,
  "n": 1
 },
 "named_place_found_in_dataset": {
  "value": 0.667,
  "n": 3
 },
 "named_place_unreachable_and_explained": {
  "value": 1.0,
  "n": 1
 },
 "hit_at_5_poi_labels": {
  "value": null,
  "n": 0
 },
 "clarification_correct": {
  "value": 1.0,
  "n": 1
 },
 "unknown_attributes_reported": {
  "value": 1.0,
  "n": 4
 },
 "plans_with_hard_constraint_violations": {
  "value": 0,
  "n": 33
 },
 "empty_no_feasible_place_with_suggestions": {
  "value": 9,
  "n": 9
 },
 "empty_because_model_failed": {
  "value": 0,
  "codes": [],
  "queries": []
 },
 "hit5_not_applicable_hard_filter": [
  "en09"
 ],
 "starts": {
  "named_dataset_place": 33,
  "simulated_coordinates": 0
 },
 "notices_ok": {
  "value": 1.0,
  "n": 1
 },
 "names_in_all_languages": {
  "value": 1.0,
  "n": 33
 },
 "replacement_kept_others": [],
 "walk_replan": [],
 "styles": [
  {
   "alternatives": 2,
   "expected_at_least": 1,
   "status": "ok",
   "all_within_budget": true,
   "all_distinct": true,
   "ok": true
  }
 ]
}
```

## Per query

| id | lang | start used | top-5 categories | plan | violations | notes |
|---|---|---|---|---|---|---|
| en01 | en | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| ru01 | ru | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| kk01 | kk | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| en02 | en | Хан Шатыр | museum, artwork, artwork | museum, artwork, artwork | — | hit5_category=True |
| ru02 | ru | Хан Шатыр | museum, artwork, artwork | museum, artwork, artwork | — | hit5_category=True |
| kk02 | kk | Хан Шатыр | museum, artwork, artwork | museum, artwork, artwork | — | hit5_category=True |
| en03 | en | EXPO <b>Sphere</b> | viewpoint, artwork, attraction, artwork, attraction | viewpoint, attraction, artwork | — | hit5_category=True |
| kk03 | kk | EXPO <b>Sphere</b> | park, park, viewpoint, artwork, attraction | park, viewpoint | — | hit5_category=True |
| en04 | en | Мега Силк Вей | park, park, attraction, attraction, viewpoint | park, attraction, park | — | named_excluded={'syn:212': 'too_far'} |
| ru04 | ru | Мега Силк Вей | attraction, attraction, viewpoint, museum, artwork | attraction, attraction, viewpoint | — | named_excluded={}; hit5_named=True |
| kk04 | kk | Мега Силк Вей | park, park, attraction, attraction, viewpoint | park, attraction, park | — | named_excluded={} |
| en05 | en | EXPO <b>Sphere</b> | cafe, cafe | cafe, cafe | — | hit5_category=True; unknown_reported=True |
| ru05 | ru | EXPO <b>Sphere</b> | cafe, cafe | cafe, cafe | — | hit5_category=True; unknown_reported=True |
| kk05 | kk | EXPO <b>Sphere</b> | cafe, cafe | cafe, cafe | — | hit5_category=True; unknown_reported=True |
| en06 | en | Хан Шатыр | attraction | attraction | — | hit5_category=True |
| ru06 | ru | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['deadline_binding', 'any_category', 'change_start'] |
| en07 | en | EXPO <b>Sphere</b> | playground, cafe, park, cafe, museum | cafe, playground, park | — | hit5_category=True |
| ru07 | ru | EXPO <b>Sphere</b> | playground, park | playground | — | hit5_category=True |
| en08 | en | Хан Шатыр | cafe, cafe | cafe, cafe | — | hit5_category=True |
| kk08 | kk | Хан Шатыр | cafe, cafe | cafe, cafe | — | hit5_category=True |
| en09 | en | EXPO <b>Sphere</b> |  |  | — | hit5_na_reason=hard filter left no eligible place (see excluded_by_code); empty_kind=no_feasible_place; empty=True; suggestions=['drop_wheelchair_filter', 'any_category', 'change_start'] |
| ru09 | ru | EXPO <b>Sphere</b> | cafe, cafe | cafe, cafe | — | hit5_category=True |
| en10 | en | EXPO <b>Sphere</b> |  |  | — | empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| ru10 | ru | Мега Силк Вей |  |  | — | clarify=start_conflict; clarify_ok=True |
| en11 | en | EXPO <b>Sphere</b> | cafe, cafe | cafe, cafe | — | hit5_category=True |
| kk11 | kk | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| en12 | en | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| ru12 | ru | Бәйтерек | park | park | — | hit5_category=True |
| en13 | en | EXPO <b>Sphere</b> | cafe, park, park, cafe, viewpoint | cafe, park, park | — | hit5_category=True; styles={'alternatives': 2, 'expected_at_least': 1, 'status': 'ok', 'all_within_budget': True, 'all_distinct': True, 'ok': True} |
| en14 | en | Бәйтерек |  |  | — | hit5_category=False; empty_kind=no_feasible_place; notice_ok=True; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| ru14 | ru | Мега Силк Вей | park, park, viewpoint, artwork, attraction | park | — | hit5_category=True |
| en15 | en | Хан Шатыр | attraction, attraction, viewpoint, artwork, artwork | attraction, attraction, viewpoint | — | unknown_reported=True |
| kk15 | kk | Хан Шатыр | playground, museum, park, artwork, artwork | museum | — | hit5_category=True |

## Samples for human review (names in 3 languages with their source kind, and the AI text)

Kinds: osm = OSM name:xx tag; original = original name shown unchanged; osm_latin = Latin name from OSM;
wikidata = checked Wikidata label; override = reviewed. ≈ = labelled descriptive translation.

* **en02** (museum, text: calc): kk «Synthetic museum 6 [original]» · ru «Synthetic museum 6 [original]» · en «Synthetic museum 6 [original]»<br>warnings: no_why
* **en02** (artwork, text: calc): kk «Synthetic artwork 8 [original]» · ru «Synthetic artwork 8 [original]» · en «Synthetic artwork 8 [original]»<br>warnings: no_why
* **en02** (artwork, text: calc): kk ««Астана Жұлдызы» ескерткіші [original]» · ru ««Астана Жұлдызы» ескерткіші [original]» · en ««Астана Жұлдызы» ескерткіші [original]»<br>warnings: no_why
* **ru02** (museum, text: calc): kk «Synthetic museum 6 [original]» · ru «Synthetic museum 6 [original]» · en «Synthetic museum 6 [original]»<br>warnings: no_why
* **ru02** (artwork, text: calc): kk «Synthetic artwork 8 [original]» · ru «Synthetic artwork 8 [original]» · en «Synthetic artwork 8 [original]»<br>warnings: no_why
* **ru02** (artwork, text: calc): kk ««Астана Жұлдызы» ескерткіші [original]» · ru ««Астана Жұлдызы» ескерткіші [original]» · en ««Астана Жұлдызы» ескерткіші [original]»<br>warnings: no_why
* **kk02** (museum, text: calc): kk «Synthetic museum 6 [original]» · ru «Synthetic museum 6 [original]» · en «Synthetic museum 6 [original]»<br>warnings: no_why
* **kk02** (artwork, text: calc): kk «Synthetic artwork 8 [original]» · ru «Synthetic artwork 8 [original]» · en «Synthetic artwork 8 [original]»<br>warnings: no_why
* **kk02** (artwork, text: calc): kk ««Астана Жұлдызы» ескерткіші [original]» · ru ««Астана Жұлдызы» ескерткіші [original]» · en ««Астана Жұлдызы» ескерткіші [original]»<br>warnings: no_why
* **en03** (viewpoint, text: calc): kk «Synthetic viewpoint 7 [original]» · ru «Synthetic viewpoint 7 [original]» · en «Synthetic viewpoint 7 [original]»<br>warnings: no_why
* **en03** (attraction, text: calc): kk «Хан Шатыр [original]» · ru «Хан Шатыр [original]» · en «Khan Shatyr [osm_latin]»<br>warnings: no_why
* **en03** (artwork, text: calc): kk «А. С. Пушкину [original]» · ru «А. С. Пушкину [original]» · en «А. С. Пушкину [original]»<br>warnings: no_why
* **kk03** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **kk03** (viewpoint, text: calc): kk «Synthetic viewpoint 7 [original]» · ru «Synthetic viewpoint 7 [original]» · en «Synthetic viewpoint 7 [original]»<br>warnings: no_why
* **en04** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **en04** (attraction, text: calc): kk «Хан Шатыр [original]» · ru «Хан Шатыр [original]» · en «Khan Shatyr [osm_latin]»<br>warnings: no_why
* **en04** (park, text: calc): kk «Synthetic park 4 [original]» · ru «Synthetic park 4 [original]» · en «Synthetic park 4 [original]»<br>warnings: no_why
* **ru04** (attraction, text: calc): kk «EXPO <b>Sphere</b> [original]» · ru «EXPO <b>Sphere</b> [original]» · en «EXPO <b>Sphere</b> [original]»<br>warnings: no_why
* **ru04** (attraction, text: calc): kk «Хан Шатыр [original]» · ru «Хан Шатыр [original]» · en «Khan Shatyr [osm_latin]»<br>warnings: no_why
* **ru04** (viewpoint, text: calc): kk «Synthetic viewpoint 7 [original]» · ru «Synthetic viewpoint 7 [original]» · en «Synthetic viewpoint 7 [original]»<br>warnings: no_why
* **kk04** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **kk04** (attraction, text: calc): kk «Хан Шатыр [original]» · ru «Хан Шатыр [original]» · en «Khan Shatyr [osm_latin]»<br>warnings: no_why
* **kk04** (park, text: calc): kk «Synthetic park 4 [original]» · ru «Synthetic park 4 [original]» · en «Synthetic park 4 [original]»<br>warnings: no_why
* **en05** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **en05** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **ru05** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **ru05** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **kk05** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **kk05** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **en06** (attraction, text: calc): kk «Атырау көпірі [osm]» · ru «Атырау көпірі [original]» · en «Атырау көпірі [original] ≈Atyrau Bridge»<br>warnings: no_why
* **en07** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **en07** (playground, text: calc): kk «Synthetic playground 5 [original]» · ru «Synthetic playground 5 [original]» · en «Synthetic playground 5 [original]»<br>warnings: no_why
* **en07** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **ru07** (playground, text: calc): kk «Synthetic playground 5 [original]» · ru «Synthetic playground 5 [original]» · en «Synthetic playground 5 [original]»<br>warnings: no_why
* **en08** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **en08** (cafe, text: calc): kk «Coffee Boom [original]» · ru «Coffee Boom [original]» · en «Coffee Boom [original]»<br>warnings: no_why
* **kk08** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **kk08** (cafe, text: calc): kk «Coffee Boom [original]» · ru «Coffee Boom [original]» · en «Coffee Boom [original]»<br>warnings: no_why
* **ru09** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **ru09** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **en11** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **en11** (cafe, text: calc): kk «Synthetic cafe 1 [original]» · ru «Synthetic cafe 1 [original]» · en «Synthetic cafe 1 [original]»<br>warnings: no_why
* **ru12** (park, text: calc): kk «Synthetic park 12 [original]» · ru «Synthetic park 12 [original]» · en «Synthetic park 12 [original]»<br>warnings: no_why
* **en13** (cafe, text: calc): kk «Кофе Бум [original]» · ru «Кофе Бум [original]» · en «Кофе Бум [original]»<br>warnings: no_why
* **en13** (park, text: calc): kk «Synthetic park 4 [original]» · ru «Synthetic park 4 [original]» · en «Synthetic park 4 [original]»<br>warnings: no_why
* **en13** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **ru14** (park, text: calc): kk «Synthetic park 3 [original]» · ru «Synthetic park 3 [original]» · en «Synthetic park 3 [original]»<br>warnings: no_why
* **en15** (attraction, text: calc): kk «Атырау көпірі [osm]» · ru «Атырау көпірі [original]» · en «Атырау көпірі [original] ≈Atyrau Bridge»<br>warnings: no_why
* **en15** (attraction, text: calc): kk «EXPO <b>Sphere</b> [original]» · ru «EXPO <b>Sphere</b> [original]» · en «EXPO <b>Sphere</b> [original]»<br>warnings: no_why
* **en15** (viewpoint, text: calc): kk «Synthetic viewpoint 7 [original]» · ru «Synthetic viewpoint 7 [original]» · en «Synthetic viewpoint 7 [original]»<br>warnings: no_why
* **kk15** (museum, text: calc): kk «Synthetic museum 6 [original]» · ru «Synthetic museum 6 [original]» · en «Synthetic museum 6 [original]»
