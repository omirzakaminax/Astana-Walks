# Evaluation: real-lexical-live

Measured by eval/run_eval.py. Nothing here is estimated.

* dataset: C:\hack\astana-walks\data\pois.json
* dataset_kind: real
* places: 504
* dataset_collected_at: 2026-10-20T15:30:27+00:00
* executed_at_astana_time: 2026-10-20 22:04
* simulated_planning_time: 2026-10-21 14:30 (Wednesday) — fixed scenario clock (use --now to change)
* retrieval_mode_requested: lexical
* retrieval_mode_used: ['lexical']
* model: qwen3:4b-instruct
* labels: category-level (eval/queries.json label_rules)

## Summary

```json
{
 "queries": 33,
 "hit_at_5_category": {
  "value": 1.0,
  "n": 26
 },
 "hit_at_5_named_place": {
  "value": 0.0,
  "n": 1
 },
 "named_place_found_in_dataset": {
  "value": 1.0,
  "n": 3
 },
 "named_place_unreachable_and_explained": {
  "value": 1.0,
  "n": 2
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
  "value": 4,
  "n": 4
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
  "named_dataset_place": 21,
  "simulated_coordinates": 12
 },
 "notices_ok": {
  "value": 1.0,
  "n": 1
 },
 "names_in_all_languages": {
  "value": 1.0,
  "n": 33
 },
 "replacement_kept_others": [
  {
   "ok": true,
   "others_kept": true,
   "within_budget": true
  }
 ],
 "walk_replan": [
  {
   "ok": true,
   "returns_to_original": true,
   "within_remaining_time": true
  }
 ],
 "styles": [
  {
   "alternatives": 1,
   "expected_at_least": 1,
   "status": "ok",
   "all_within_budget": true,
   "all_distinct": true,
   "ok": true
  }
 ],
 "model": {
  "valid_source_id_rate": {
   "value": 1.0,
   "n_items": 39
  },
  "malformed_after_repair": {
   "value": 0,
   "n": 33
  },
  "repair_attempts": 0,
  "removed_unsupported_claims": 1,
  "wrong_language_warnings": 0,
  "other_errors": [],
  "output_tokens_max": 235,
  "hit_output_cap": [],
  "latency_s": {
   "first_call_incl_loading": 6.3,
   "later_calls_median": 5.69,
   "calls": 35
  }
 }
}
```

## Per query

| id | lang | start used | top-5 categories | plan | violations | notes |
|---|---|---|---|---|---|---|
| en01 | en | Бәйтерек | park, cafe, cafe, fountain | cafe, fountain | — | hit5_category=True; model_tokens={'prompt': 1052, 'output': 148, 'done_reason': 'stop'} |
| ru01 | ru | Бәйтерек | park, cafe, cafe, fountain | cafe, fountain | — | hit5_category=True; model_tokens={'prompt': 1075, 'output': 144, 'done_reason': 'stop'} |
| kk01 | kk | Бәйтерек | park, cafe, cafe, fountain | cafe, fountain | — | hit5_category=True; model_tokens={'prompt': 1229, 'output': 139, 'done_reason': 'stop'} |
| en02 | en | Хан Шатыр | gallery, gallery, arts_centre, artwork, artwork | gallery, gallery | — | hit5_category=True; model_tokens={'prompt': 1126, 'output': 120, 'done_reason': 'stop'} |
| ru02 | ru | Хан Шатыр | gallery, gallery, arts_centre, artwork, artwork | gallery, gallery | — | hit5_category=True; model_tokens={'prompt': 1204, 'output': 135, 'done_reason': 'stop'} |
| kk02 | kk | Хан Шатыр | gallery, gallery, arts_centre, artwork, artwork | gallery, gallery | — | hit5_category=True; model_tokens={'prompt': 1344, 'output': 231, 'done_reason': 'stop'} |
| en03 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | attraction | attraction | — | hit5_category=True; model_tokens={'prompt': 602, 'output': 51, 'done_reason': 'stop'} |
| kk03 | kk | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | park, park, attraction | attraction | — | hit5_category=True; model_tokens={'prompt': 974, 'output': 170, 'done_reason': 'stop'} |
| en04 | en | Mega Silk Way | park, attraction, park, attraction, fountain | attraction | — | named_excluded={'osm:way/230401645': 'too_far'}; model_tokens={'prompt': 1378, 'output': 114, 'done_reason': 'stop'} |
| ru04 | ru | Mega Silk Way | attraction, attraction, artwork, artwork |  | — | named_excluded={'osm:way/460703779': 'too_far'}; empty_kind=no_feasible_place; model_tokens={'prompt': 1087, 'output': 46, 'done_reason': 'stop'}; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| kk04 | kk | Mega Silk Way | park, attraction, park, attraction, fountain | attraction | — | named_excluded={}; hit5_named=False; model_tokens={'prompt': 1645, 'output': 140, 'done_reason': 'stop'} |
| en05 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 805, 'output': 65, 'done_reason': 'stop'}; unknown_reported=True |
| ru05 | ru | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 843, 'output': 82, 'done_reason': 'stop'}; unknown_reported=True |
| kk05 | kk | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 903, 'output': 120, 'done_reason': 'stop'}; unknown_reported=True |
| en06 | en | Хан Шатыр | attraction, attraction, artwork, artwork | attraction | — | hit5_category=True; model_tokens={'prompt': 973, 'output': 53, 'done_reason': 'stop'} |
| ru06 | ru | Бәйтерек | park, fountain | park | — | hit5_category=True; model_tokens={'prompt': 745, 'output': 64, 'done_reason': 'stop'} |
| en07 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | playground, cafe, park, cafe, park | playground, cafe | — | hit5_category=True; model_tokens={'prompt': 1158, 'output': 126, 'done_reason': 'stop'} |
| ru07 | ru | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | playground, park | playground | — | hit5_category=True; model_tokens={'prompt': 743, 'output': 90, 'done_reason': 'stop'} |
| en08 | en | Хан Шатыр | cafe, cafe | cafe, cafe | — | hit5_category=True; model_tokens={'prompt': 745, 'output': 128, 'done_reason': 'stop'} |
| kk08 | kk | Хан Шатыр | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 822, 'output': 102, 'done_reason': 'stop'} |
| en09 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) |  |  | — | hit5_na_reason=hard filter left no eligible place (see excluded_by_code); empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'drop_wheelchair_filter', 'any_category', 'change_start'] |
| ru09 | ru | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 862, 'output': 88, 'done_reason': 'stop'} |
| en10 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) |  |  | — | empty_kind=no_feasible_place; empty=True; suggestions=['add_time', 'any_category', 'change_start'] |
| ru10 | ru | Mega Silk Way |  |  | — | clarify=start_conflict; clarify_ok=True |
| en11 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | cafe, cafe | cafe | — | hit5_category=True; model_tokens={'prompt': 807, 'output': 64, 'done_reason': 'stop'} |
| kk11 | kk | Бәйтерек | park, cafe, cafe, park, fountain | cafe, fountain | — | hit5_category=True; model_tokens={'prompt': 1596, 'output': 235, 'done_reason': 'stop'} |
| en12 | en | Бәйтерек | attraction, attraction, museum, gallery, gallery | attraction | — | hit5_category=True; model_tokens={'prompt': 1351, 'output': 225, 'done_reason': 'stop'}; replace={'ok': True, 'others_kept': True, 'within_budget': True} |
| ru12 | ru | Бәйтерек | park, cafe, cafe, park, fountain | park, cafe | — | hit5_category=True; model_tokens={'prompt': 1369, 'output': 116, 'done_reason': 'stop'}; walk_replan={'ok': True, 'returns_to_original': True, 'within_remaining_time': True} |
| en13 | en | SIMULATED point: EXPO / Astana IT University area (the collector's default centre) (51.089, 71.416) | park, cafe, park, cafe, attraction | cafe, park | — | hit5_category=True; model_tokens={'prompt': 1254, 'output': 128, 'done_reason': 'stop'}; styles={'alternatives': 1, 'expected_at_least': 1, 'status': 'ok', 'all_within_budget': True, 'all_distinct': True, 'ok': True} |
| en14 | en | Бәйтерек | attraction, attraction, museum, gallery, gallery | attraction | — | hit5_category=True; model_tokens={'prompt': 1358, 'output': 220, 'done_reason': 'stop'}; notice_ok=True |
| ru14 | ru | Mega Silk Way | park, park, attraction | park | — | hit5_category=True; model_tokens={'prompt': 887, 'output': 66, 'done_reason': 'stop'} |
| en15 | en | Хан Шатыр | attraction, attraction, gallery, gallery, artwork |  | — | empty_kind=no_feasible_place; model_tokens={'prompt': 1281, 'output': 60, 'done_reason': 'stop'}; unknown_reported=True; empty=True; suggestions=['add_time', 'any_category', 'hours_info', 'change_start'] |
| kk15 | kk | Хан Шатыр | ice_cream, ice_cream, theme_park, playground, gallery | theme_park | — | hit5_category=True; model_tokens={'prompt': 1431, 'output': 179, 'done_reason': 'stop'} |

## Samples for human review (names in 3 languages with their source kind, and the AI text)

Kinds: osm = OSM name:xx tag; original = original name shown unchanged; osm_latin = Latin name from OSM;
wikidata = checked Wikidata label; override = reviewed. ≈ = labelled descriptive translation.

* **en01** (cafe, text: ai): kk «Лепим и варим [original]» · ru «Лепим и варим [original]» · en «Лепим и варим [original]»<br>why: It is a cafe offering coffee and is close to the starting point. A short walk after can be combined with coffee.<br>activity: Enjoy a coffee at a cafe and take a short walk through the park.
* **en01** (fountain, text: ai): kk «Әнші субұрқақтар [original]» · ru «Поющий фонтан [osm]» · en «Әнші субұрқақтар [original]»<br>why: It's within walking distance and takes only a few minutes to reach. A short visit fits well within your 45-minute time budget.<br>activity: Visit the fountain and enjoy a coffee nearby.
* **ru01** (cafe, text: ai): kk «Лепим и варим [original]» · ru «Лепим и варим [original]» · en «Лепим и варим [original]»<br>why: Кафе предлагает кофе и русскую кухню. Близко от центра, легко добраться за 7 минут.<br>activity: Посетить кафе и попробовать русскую кухню
* **ru01** (fountain, text: ai): kk «Әнші субұрқақтар [original]» · ru «Поющий фонтан [osm]» · en «Әнші субұрқақтар [original]»<br>why: Расстояние 340 метров — подходит для 45 минут. Прогулка и фонтан соответствуют интересам кофе и парка.<br>activity: Посмотреть поющий фонтан и пройти короткую прогулку вокруг него
* **kk01** (cafe, text: ai): kk «Degirmen [original]» · ru «Degirmen [original]» · en «Degirmen [original]»<br>why: Кофе қажет, және қарап тұрып жатады<br>activity: Кофе ішіп, қарап тұрыңыз
* **kk01** (fountain, text: ai): kk «Әнші субұрқақтар [original]» · ru «Поющий фонтан [osm]» · en «Әнші субұрқақтар [original]»<br>why: 45 минут бар, әрі қарай жүріп өтетін жерде. Кофе және жерде қалуға тиімді барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері барынша құнды жері<br>activity: Кофе ішіп, Әнші субұрқақтарға барып, тұрып қалып қойыңыз
* **en02** (gallery, text: ai): kk «Көрме [original]» · ru «Корме [osm]» · en «Korme [osm]»<br>why: It is an art gallery and indoor, suitable for culture and art interests.<br>activity: Explore the art collection
* **en02** (gallery, text: ai): kk «Астана-Экспо КС [original]» · ru «Астана-Экспо КС [original]» · en «Астана-Экспо КС [original]»<br>why: It is an art gallery and indoor, ideal for art and culture enthusiasts.<br>activity: View the art exhibits
* **ru02** (gallery, text: ai): kk «Көрме [original]» · ru «Корме [osm]» · en «Korme [osm]»<br>why: Это галерея, которая специализируется на искусстве. Подходит для интересов пользователя.<br>activity: Посмотреть выставку в галерее
* **ru02** (gallery, text: ai): kk «Астана-Экспо КС [original]» · ru «Астана-Экспо КС [original]» · en «Астана-Экспо КС [original]»<br>why: Это галерея, посвящённая искусству. Отлично подходит для культурных интересов.<br>activity: Посмотреть выставку в галерее
* **kk02** (gallery, text: ai): kk «Көрме [original]» · ru «Корме [osm]» · en «Korme [osm]»<br>why: Галерея, мұражай түрінде; әртүрлі әріптерді қарастыруға мүмкіндік береді<br>activity: Көрме галереясында әртүрлі әріптерді қарастыру
* **kk02** (gallery, text: ai): kk «Астана-Экспо КС [original]» · ru «Астана-Экспо КС [original]» · en «Астана-Экспо КС [original]»<br>why: Галерея, мұражай түрінде; әртүрлі әріптерді қарастыруға мүмкіндік береді<br>activity: Астана-Экспо КС-те әртүрлі әріптерді қарастыру
* **en03** (attraction, text: ai): kk «Тәуелсіздіктің 25 жылдығы [original]» · ru «25-ти летие Независимости [osm]» · en «25th Anniversary of Independence [osm]»<br>why: It is an indoor attraction, so it avoids outdoor parks.<br>activity: Explore the attraction
* **kk03** (attraction, text: ai): kk «Тәуелсіздіктің 25 жылдығы [original]» · ru «25-ти летие Независимости [osm]» · en «25th Anniversary of Independence [osm]»<br>why: Бұл қорытынды орын, ішкі жерде жатады және 60 минут ішінде жүріп өтіп, бастапқы нүктеге қайтуға болады.<br>activity: Көрікті орында қайталау жасау
* **en04** (attraction, text: ai): kk «Мәңгілік ел қақпасы [wikidata]» · ru «Триумфальная арка Мангилик Ел [osm]» · en «Mäñgilik El Triumphal Arch [osm]»<br>why: Baiterek is a major landmark in Astana, and this entry matches the request directly.<br>activity: Visit the Baiterek monument at the center of Astana
* **kk04** (attraction, text: ai): kk «Мәңгілік ел қақпасы [wikidata]» · ru «Триумфальная арка Мангилик Ел [osm]» · en «Mäñgilik El Triumphal Arch [osm]»<br>why: Мәңгілік ел қақпасы Хазірет Сұлтан мешітінің жағында орналасқан<br>activity: Нұрсұлтан Назарбаевтың ескерткішін қараңыз
* **en05** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: It is a cafe with coffee, and indoor.<br>activity: Work at a table with a coffee
* **ru05** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: Кафе с кофе, находится в помещении. Открыто сейчас.<br>activity: Поработать над заданием
* **kk05** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: Кафе, қолданылатын және жұмыс істеу үшін ыңғайлы<br>activity: Кафеға келіп, жұмыс істеу үшін қолдану
* **en06** (attraction, text: ai): kk «Конвой [original]» · ru «Конвой [original]» · en «Конвой [original]»<br>why: Close to starting point and indoor, suitable for a quick walk.<br>activity: Visit the attraction briefly
* **ru06** (park, text: ai): kk «Сквер [original]» · ru «Сквер [original]» · en «Сквер [original]»<br>why: Парк близок к Байтереку и подходит для прогулки.<br>activity: Прогуляться по парку
* **en07** (playground, text: ai): kk «Балалар алаңы (OSM-де атауы жоқ) [generated]» · ru «Детская площадка (без названия в OSM) [generated]» · en «Playground (no name in OpenStreetMap) [generated]»<br>why: It is a dedicated playground for children. Close to starting point.<br>activity: Let kids play on the playground equipment
* **en07** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: It is a coffee cafe suitable for someone with kids. Near the playground.<br>activity: Enjoy coffee in a cafe with kids-friendly atmosphere
* **ru07** (playground, text: ai): kk «Балалар алаңы (OSM-де атауы жоқ) [generated]» · ru «Детская площадка (без названия в OSM) [generated]» · en «Playground (no name in OpenStreetMap) [generated]»<br>why: Это детская площадка, подходит для детей.<br>activity: Играть на детской площадке
* **en08** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [original]»<br>why: It's freezing outside, and this indoor cafe offers warmth and comfort.<br>activity: Enjoy a warm coffee in a cozy indoor cafe.
* **en08** (cafe, text: ai): kk «Cups coffee [original]» · ru «Cups coffee [original]» · en «Cups coffee [original]»<br>why: It's freezing outside, and this indoor cafe offers warmth and comfort.<br>activity: Enjoy a warm coffee in a cozy indoor cafe.
* **kk08** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [original]»<br>why: Бұл үйдің ішінде жылы жер керек<br>activity: Суық жерде қалыпты жылы жер керек, бұл күнде қалыпты жылы жер керек
* **ru09** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: Это кафе по типу кофейни. Открыто по данным OpenStreetMap.<br>activity: Пить кофе
* **en11** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: It is a coffee shop and easily accessible.<br>activity: Enjoy a cup of coffee at a cozy cafe
* **kk11** (cafe, text: ai): kk «Master Coffee [original]» · ru «Master Coffee [original]» · en «Master Coffee [original]»<br>why: Кофе үшін жақын және ашық. Қайта қайтадан қалып қойыңыз үшін жақын.<br>activity: Кофе ішіп, қайта қайтадан қалып қойыңыз
* **kk11** (fountain, text: ai): kk «Әнші субұрқақтар [original]» · ru «Поющий фонтан [osm]» · en «Әнші субұрқақтар [original]»<br>why: 340 метр арақашы, 6 минут жүріп өтіңіз. Көптеген кофе үшін жақын жерде жатады, саябақта серуен үшін тиімді басқа жерлерге қарауға болады<br>activity: Субұрқақта әрі қарай жүріп өтіңіз
* **en12** (attraction, text: ai): kk «Мәңгілік ел қақпасы [wikidata]» · ru «Триумфальная арка Мангилик Ел [osm]» · en «Mäñgilik El Triumphal Arch [osm]»<br>why: It is a famous landmark and a major monument in Astana, symbolizing national independence.<br>activity: Visit the Mäñgilik El Triumphal Arch to see the 20-meter-tall monument marking Kazakhstan's 20th independence anniversary.
* **ru12** (park, text: ai): kk «Сквер [original]» · ru «Сквер [original]» · en «Сквер [original]»<br>why: Это парк, где можно погулять. Близко от начальной точки.<br>activity: Погулять в парке
* **ru12** (cafe, text: ai): kk «Лепим и варим [original]» · ru «Лепим и варим [original]» · en «Лепим и варим [original]»<br>why: Это кафе, где можно попробовать кофе. Близко от начальной точки.<br>activity: Выпить кофе в кафе
* **en13** (cafe, text: ai): kk «Starbucks [original]» · ru «Starbucks [original]» · en «Starbucks [osm]»<br>why: It is a cafe offering coffee and is close to the starting point.<br>activity: Enjoy a coffee at a cafe in the park.
* **en13** (park, text: ai): kk «Бейбітшілік пен келісім аллеясы [osm]» · ru «Аллея мира и согласия [osm]» · en «Бейбітшілік пен Келісім аллеясы [original]»<br>why: It is a park suitable for walking and offers a green space.<br>activity: Stroll through the park and enjoy the outdoor space.
* **en14** (attraction, text: ai): kk «Мәңгілік ел қақпасы [wikidata]» · ru «Триумфальная арка Мангилик Ел [osm]» · en «Mäñgilik El Triumphal Arch [osm]»<br>why: It is a major landmark and symbol of national pride, suitable for a quick tourist stop.<br>warnings: ungrounded:ratings
* **ru14** (park, text: ai): kk «NU Park [original]» · ru «NU Park [original]» · en «NU Park [original]»<br>why: Близко от Мега Силк Вей, парк подходит для прогулки.<br>activity: Прогуляться по парку
* **kk15** (theme_park, text: ai): kk «Fame City [original]» · ru «Fame City [original]» · en «Fame City [original]»<br>why: Балалар алаңына ұсынылған, баламен бірге ойнап өтуге тиімді<br>activity: Ойын-сауық паркінде ойындарды ойнап өтіңіз
