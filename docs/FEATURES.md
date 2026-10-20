# Feature guide, architecture and constraint precedence

## Architecture in one picture

```
browser (web/)                         server.py (standard library)              walks/ (pure Python)
-------------                          ----------------------------              --------------------
start picker (search)           ──►  GET  /api/places      ─► search.Index (names, aliases, spellings)
sentence builder, More options  ──►  POST /api/recommend  ─┐   (named place far from the start -> one question)
card actions (Replace, …)       ──►  POST /api/replace     ├─► constraints.resolve()  (validate + precedence)
Remove / style / "I'm here"     ──►  POST /api/replan      ┘        │
                                                                     ▼
                                                     retrieval.retrieve()   hard filters + BM25 ranking
                                                                     │       (pace, exclusions, "no …", hours at arrival,
                                                                     │        outdoor limit, source filters, weather,
                                                                     │        named places, optional semantic RRF)
                                                                     ▼
                                                     LLM (Ollama, JSON Schema) selects from evidence P1..P6
                                                     (≤ 1 repair), or the app selects (Surprise / Replace /
                                                     group / multi-intent cover / style) and the LLM only
                                                     explains; grounding.check() removes unsupported sentences
                                                                     ▼
                                                     itinerary.fit_plan()   ONE canonical plan:
                                                                             order, visit minutes, legs,
                                                                             arrival times, outdoor minutes
                                                                     ▼
cards, map numbers, timeline, ◄──────── JSON: plan{stops(+fit facts, display_names), legs, total…},
export, Bingo, styles, walk               styles, suggestions, constraints, trace(+timings, mode)
```

Everything the user sees about a plan comes from `plan` in the response. The page never
recalculates durations itself; it only re-renders the server's plan.

## Constraint precedence (walks/constraints.py)

1. **Base time**: a duration in the request text ("2 hours") if present, otherwise the time
   setting. In group mode: the shortest participant's time; text can only shorten it.
2. **Hard caps** that can only shorten the plan, never lengthen it:
   * group: the shortest available time;
   * "back by": minutes until the return time minus the buffer.
   `effective time = min(base, caps)`. The response says which one won (`budget_source`).
3. **Pace**: the slowest pace of the group (solo: the chosen pace).
4. **Return**: a "back by" time always means returning to the start point.
5. **Outdoor limit**: a hard cap on estimated outdoor minutes. Never relaxed automatically; the
   page offers explicit "Allow N min outdoors" and "Remove the outdoor limit" buttons.
6. **Exclusions** (start point, visited, reported unavailable, removed/replaced, already in the
   plan) are never reintroduced until the user presses "Reset visited and excluded places".
7. **Negations and source filters** ("no cafes", "only places with known hours", "OSM wheelchair
   tag") are hard filters. When nothing fits, the page lists what ruled places out and offers
   explicit one-click changes with a preview ("Add 15 min (60 → 75 min)"); a deadline is never
   offered as something to drop.
8. **Active walk** ("I'm here"): replans from the current position (last place marked done, or the
   device location after an explicit click) with the remaining time — the deadline is recomputed
   from now — and still returns to the ORIGINAL start.

All of this is validated on the server (types, ranges, IDs, 2–5 participants, deadline format).

## The canonical itinerary (walks/itinerary.py)

* total = every walking leg (including the way back) + every visit duration shown on the cards;
* up to three stops: every order is tried, the shortest feasible one wins;
* if it does not fit: visits are shortened in 5-minute steps (never below the category minimum;
  the cards then show the shortened value and a note explains why), then the lowest-priority
  stops are dropped (also explained);
* opening hours are checked at the estimated **arrival** time for the **whole visit**;
  unknown hours are shown as unknown, never as open;
* walking = straight-line distance × 1.3 at the request's pace: an estimate, not navigation.

## The eight features

| # | Feature | Where to find it | How it works |
|---|---|---|---|
| 1 | **Back by…** | More options → "Be back by a set time" | Date (default today), time (Astana), buffer (default 10). Server computes minutes left; `cap = left − buffer`. Past, more than 24 h ahead, or buffer ≥ time left → clear error. The plan shows the return ETA and a live countdown (no model calls); when the plan no longer fits, a "Recalculate" button rechecks on the server. |
| 2 | **Replace one place** | Buttons on each card | Replace / Already visited / Closed or unavailable / Too far (only closer places) / Remove. The other places and their durations are kept when feasible; the whole plan is recalculated. No fit → message + Remove. A "closed" report is session-only and marked on the card until replaced or removed. |
| 3 | **Don't let me freeze** | More options → outdoor limit | Presets 5/10/15/20/30 min or custom; optional strict mode. Outdoor = all walking + time at outdoor places. Indoor status is from OSM tags when present, otherwise estimated from the type, and labelled as such. Applied while building the plan. |
| 4 | **Surprise me** | Button next to "Find places" | No text needed. Real records → seeded shuffle → varied (different types), feasible plan through the same checks. "Another surprise" avoids previous plans; when none are left, the page says so and offers "Start surprises over". |
| 5 | **Take this route with me** | Panel under the plan | Copy plan (with a manual-copy fallback), Save plan (self-contained HTML, no scripts or external files, all text escaped, only http/https links), Share… when the browser supports it. Exact start coordinates only with an explicit checkbox. |
| 6 | **Go together** | More options → "Go together" | 2–5 people, each with interests, time and pace. Shortest time and slowest pace win. Evidence is balanced between people; if someone is not covered, the app tries to add or swap a place for them; the plan shows who each place suits, or that time did not allow it. Turning it off clears all group settings. |
| 7 | **Walking pace** | More options → pace | Leisurely 45 / Normal 75 / Brisk 95 m per minute (planning assumptions). Used for reachability, every leg, the way back, the deadline, outdoor time, exports and group mode. Request-scoped: no global state. |
| 8 | **City Bingo** | Panel under the plan | Three optional missions from the plan's places (suggestions, not facts), marked by the user, labelled self-reported. Optional "walk passport" stored on this device only after opt-in, with delete. After a replacement, the new place's mission starts unchecked. |

## Data quality fixes in this version

* **Duplicates**: places mapped twice (node + building, or Cyrillic and Latin name) are merged by
  cross-script name matching + distance + category, both when collecting and when loading an
  existing `data/pois.json`. Names that differ only by a number stay separate.
* **Names in the chosen language**: replaced in version 5 by the provenance-aware policy in
  `docs/NAMING.md` (no transliteration is ever presented as an English name).
* **Must-see places across the city**: `collect_osm.py --all` adds the centre and right-bank areas
  plus a citywide pass for notable places (anything OSM links to Wikipedia/Wikidata, all named
  museums, attractions and viewpoints, mosques and cathedrals with Wikidata). "Notable" is a
  factual link, shown as such; it is not a popularity rating.

## Photos and short descriptions (open sources only)

* `walks/enrich.py` (run at the end of `collect_osm.py --all`, or alone with `scripts/enrich_wiki.py`)
  reads the Wikidata links that OpenStreetMap keeps on notable places and saves into
  `data/pois.json`:
  * a **photo** from Wikimedia Commons (main image P18, or OSM `wikimedia_commons`/`image` if it is a
    Commons file) with **author and licence**; a photo without a licence is not used;
  * a **short description** in kk/ru/en: the first two sentences of the Wikipedia article, or the
    Wikidata description if there is no article; with a link to the source;
  * Wikidata labels, stored separately with an **identity check** (not a person/namesake; coordinates
    within 2 km). Only labels that pass are shown as names (`docs/NAMING.md`).
* Cards show the photo with "Photo: author, licence, Wikimedia Commons" and an "About this place" block
  with a "From Wikipedia/Wikidata" badge. If an image fails to load (offline), it is hidden.
* Descriptions are also given to the model as evidence and included in exports; photos are not part
  of the offline export (they would need internet).
* Never used: Google Maps, 2GIS or Instagram photos (copyrighted, licence unknown), or AI images.
* Privacy: like map tiles, the browser loads photos from Wikimedia's servers, which see the
  visitor's IP address; no coordinates or requests are sent to them.


## Version 5 additions

| Improvement | Where | How it works |
|---|---|---|
| Provenance-aware names | everywhere a name appears | `walks/names.py` resolves one name per language with its source (override → OSM `name:xx` → checked Wikidata label → OSM Latin name → original + type). The API sends all three languages; the page never transliterates. |
| Searchable start picker | the sentence at the top | Combobox with keyboard (↑ ↓ Enter Esc), touch, loading/no-match states. Suggestions grouped as "Suggested starting points", "Linked to Wikipedia/Wikidata", "Other sights" (no popularity claim). Searches the dataset only. |
| Start on the map | "Point on the map" | Click sets an editable coordinate start; shaded circles show the collected areas. |
| Query understanding | request text | Negations in kk/ru/en, "then"/"потом"/"кейін" order, named places as destinations, unsupported asks as unknown, one clarification when the text names a different start. |
| Grounding | each card | Clause-level claim check mapped to evidence fields; unsupported sentences removed (the card says what was removed); calculated "How it fits" list (interests, walk, time left, hours, indoor basis, unknowns). |
| Structured output + repair | model call | JSON Schema with the allowed evidence IDs (Ollama ≥ 0.5), temperature 0.1, at most one repair attempt, then a transparent failure with search-only results. |
| Plan styles | panel "Other ways to do this walk" | Less walking / More variety / Less time outdoors from the same eligible places, same constraints, comparable numbers; switching recalculates the ONE canonical plan and explains only new stops. |
| Walking directions | each card + route panel | Google Maps URL (`api=1`, `travelmode=walking`, waypoints) and OpenStreetMap foot routing for one leg; opened only on click; a private start is included only with consent. |
| "I'm here" | "Start this walk" | Self-reported progress, replan the rest from the last place or the device location (after a click), return to the original start, remaining time / deadline. No background tracking. |
| Empty results | when nothing fits | What ruled places out + one-click changes with previews; deadlines and negations are never dropped. |
| Source filters | More options | Known opening hours; OSM wheelchair = yes/limited (source-reported; route not checked; missing = unknown). |
| Report a problem | each card | Local-only report (POI ID, field, proposed value, reason, optional source URL), download as JSON, delete. No coordinates or query history. |
| Data pipeline | collector, loader, enrichment | All name variants kept with language tags; validation with skip reasons; conservative merges with reasons; backups before saving; Wikimedia cache; identity check; `scripts/data_report.py` audit. |
| Optional hybrid retrieval | `RETRIEVAL_MODE=hybrid` | multilingual-e5-small (query:/passage: prefixes), cached embeddings, RRF with the lexical rank, after the hard filters. Falls back to lexical and says so. Not the default. |
| Diagnostics and evaluation | `scripts/doctor.py`, `eval/run_eval.py` | Dependency/dataset/model checks with measured latency; 29-query KK/RU/EN evaluation with documented labels. |

## Version 6: Discover — a visual identity of its own

- **Place of the day.** One place with a free-licensed Wikimedia photo, chosen by today's date (hash of the date), so everyone sees the same pick that day. It is *not* a ranking, and the card says so. Buttons: "Start my walk here" and "Plan a walk there".
- **Astana in photos.** A gallery of every dataset place that has a licensed photo (`/api/gallery`, up to 60). Tap a photo → a dialog says what the place is: name in your language, type, description with its source badge, photo author and licence.
- **Guess the place.** A quiz mode over the same gallery: names are hidden (also in alt text), three options, a verdict in words, and a score. Nothing is stored.
- **Look.** A line drawing of the skyline (Khan Shatyr, Baiterek, Palace of Peace and Accord, Nur Alem) in the header and a qoshqar-muiz ornament band separating the planner from Discover. The ornament and skyline are original SVG drawn for this project.
- **Honest limits.** The gallery is only as big as the number of places with Commons photos in your data (14 after the user's last `enrich_wiki.py` run). No photos are scraped or generated. Photos load from Wikimedia, so they need internet; offline you see a labelled placeholder.
