# Astana Walks — product concept, RAG approach, ethics & privacy

*Case 1 "ИИ-помощник по прогулкам в городе Астана" (НИЦ Smart City), hackathon "Build with AI".*

## Problem

Someone in Astana with a short window of free time — between classes, before a flight, with a
child — wants a quick, trustworthy answer to "what can I do nearby right now?". Map apps list
hundreds of pins without considering the time they have; generic chatbots answer confidently but
can invent places, hours and events.

## Target users

- **Students and staff** around EXPO / Astana IT University with 30–90 minute breaks.
- **Visitors and business travellers** with a few hours between meetings or before a flight.
- **Parents** looking for a nearby playground, park or museum for a fixed amount of time.

## Value proposition

1–3 concrete, *checkable* suggestions in a few seconds:

- each place is real, from our own collected dataset, with a link to its source record;
- distance and walking time are computed by code and labelled as approximate;
- opening hours are shown as the source states them, with explicit uncertainty;
- the "why" and "what to do" are clearly marked as AI-generated;
- unsupported wishes (sockets, quietness, prices, live events) are flagged as unknown instead of
  being invented.

## Accessibility and languages

- Interface in **Kazakh, Russian and English**; requests are understood in all three, and the AI
  text is generated in the interface language.
- **Light and dark themes** built on one blue palette.
- **Low-vision mode**: 125 % text, maximum contrast, thick focus rings and borders, underlined
  links, single-column layout, and a **read-aloud** button on every card (browser speech, offline).
- Facts are never encoded by colour alone: badges carry text and icons; the time bar has a text
  legend and a screen-reader summary.

## Planning features (version 3)

Back-by time with a buffer; replace one place (also "visited", "closed", "too far"); an outdoor-time
limit for Astana weather; Surprise me; copy or save the plan offline; group mode for 2–5 people;
walking pace; City Bingo. All share one canonical itinerary. Details and the constraint
precedence: `docs/FEATURES.md`.

## Version 5: trust and convenience

Provenance-aware place names (no transliteration passed off as English); a searchable start picker
and a start on the map; negations, "then", named places and one clarification when the start is
ambiguous; clause-level grounding that removes unsupported sentences; JSON-Schema model output with
one bounded repair; plan styles; walking-directions hand-off; an "I'm here" active walk that returns
to the original start; explained empty results with one-click changes; source-based filters; local
"report a problem"; a data-quality/naming audit, diagnostics and a 29-query evaluation set.
See `docs/FEATURES.md`, `docs/NAMING.md`, `docs/EVALUATION.md`.

## Main scenarios (demo focus)

1. **Short walk** — "I am near EXPO and have 45 minutes. Where can I walk?"
2. **Coffee with constraints** — "Хочу тихое место с кофе и розеткой" → cafés nearby, with a clear
   label that sockets and quietness are not in the data.
3. **With a child** — "I am with a child and have one hour" → playgrounds, parks, museums that fit
   the time and are not closed according to their hours.
4. **Weather-aware** ranking: in harsh weather (very cold or hot, rain/snow, strong wind; Open-Meteo,
   free) indoor places move up and the model is told about it. Astana winters make this matter.
5. Bonus: **mini-route** through the suggested places with an approximate total time and a check
   against the time budget, plus a **time bar** on each card: walk there, time at the place, walk
   back and spare time inside the user's budget.

## How the RAG works (high level)

1. **Collection (automated).** `scripts/collect_osm.py --all` queries the OpenStreetMap Overpass API
   for three areas and citywide sights, maps OSM tags to ~25 categories, keeps names (all language
   variants with provenance), coordinates, opening hours, contacts and selected tags, merges
   duplicates conservatively with recorded reasons, validates records, backs up the old file and
   saves `data/pois.json` atomically. Wikimedia photos/descriptions are added after an identity
   check. Missing descriptions become a factual *summary of OSM tags*, labelled as such.
2. **Understanding.** Kazakh/Russian/English keyword stems map the request to intents and categories;
   negations ("no cafes", "без кафе", "кафесіз") become hard filters; "then/потом/кейін" keeps the
   order; places named in the text are found by alias search (as a destination, or — with "near/рядом
   с/маңында" — as a start, which triggers one question if it conflicts); the time budget is parsed
   from text or taken from the setting.
3. **Retrieval with hard constraints (code, not AI).** For every place: straight-line distance,
   approximate walking time (distance × 1.3 detour ÷ 75 m/min), feasibility check
   (walk there [+ back] + minimum visit ≤ budget), category match, and opening-hours status in
   Astana time (closed places and places closing before a minimal visit are removed).
4. **Ranking.** `0.45 × BM25 text match + 0.35 × category fit + 0.20 × proximity`, plus small
   bonuses (indoor in harsh weather, named place, notable for "must-see"); top 6 with at most 2 per
   category and one place per name (no two branches of one chain). Optional hybrid mode fuses a local
   multilingual embedding rank with reciprocal-rank fusion, after the hard filters.
5. **Generation.** A local model (Ollama, `qwen3:4b-instruct` recommended) receives *only* those 6
   places as evidence with short IDs (P1…P6), constrained by a JSON Schema that allows only those IDs,
   at temperature 0.1. Evidence text is marked as data, not instructions. One repair attempt is
   allowed for malformed JSON or invalid IDs; then the failure is shown with search-only results.
6. **Validation.** Unknown or duplicate IDs are rejected; visit times are clamped; each clause of the
   generated text is checked against specific evidence fields (prices/free entry, ratings, sockets,
   quietness, crowds, events, Wi-Fi, wheelchair, outdoor seating, "open now", years) and unsupported
   sentences are **removed** before display, with a note. The itinerary is checked again as a whole. Names, coordinates, distances and hours
   on the card always come from the dataset. If generation fails, the app says so and shows the
   raw search results labelled as *not* AI recommendations.

No vector database is needed: with hundreds of places, BM25 + filters is fast, transparent and easy
to defend. Local embeddings are available as an optional, measured mode, not the default.

## Ethics, privacy and misinformation

| Risk | What the prototype does |
|---|---|
| Location privacy | No accounts, no query history, no server-side storage. The start point (landmark, typed coordinates or browser geolocation, which needs explicit permission) is sent only to the local server to compute distances. It is not logged and **not sent to the model**; only per-place distances are. Weather is requested for the dataset area, not the user's position. The default model runs locally. |
| Accessibility | Three languages, low-vision mode, read aloud, keyboard navigation with visible focus, no colour-only signals, reduced-motion respected. |
| Third-party API (optional Gemini) | Off by default. If enabled, only the request text and the retrieved place evidence are sent; this is stated in the sidebar. Keys only via `.env` / hosting secrets. |
| Invented places | The model can only reference retrieved IDs; anything else is rejected and shown in the trace. |
| Wrong opening hours | Shown as "according to OSM", with "data may be outdated"; unparseable or missing hours are shown as unverified/not listed — never "open now" with certainty. |
| Unsupported claims | Sockets, quietness, prices, ratings, live events are flagged as "not in our data"; generated text that claims them triggers a warning. |
| Outdated data | Each record shows its collection date (a download date, not a verification date); the collector can be re-run any time. |
| Wrong names | Names carry their source; transliteration is never shown as a translation; users can report a wrong name locally (not published automatically). |
| External directions | Opened only on click; a private start point is included only with explicit consent. |
| Accessibility claims | Only the OSM `wheelchair` tag of the place, labelled source-reported; the route is not checked; missing = unknown. |
| Safety | The assistant suggests public places only; walking times are approximate, not routes; users are told to check on site. Late-night requests get no "event" claims. |
| Source licensing | OpenStreetMap data, © OSM contributors, ODbL — attribution shown in the app. No scraping of Google Maps or 2GIS. |

## Limitations (honest)

- Coverage = what OSM contains around the chosen area; some cafés may be missing or outdated.
- No ratings/popularity (OSM has none) and no live events.
- Straight-line distance × detour factor is not a real walking route.
- A 1.5B local model writes simple text and may occasionally return invalid JSON (handled, but
  the user must retry). Answer quality depends on the laptop and model size.
- Keyword understanding is rule-based; unusual phrasings may fall back to "general walk"
  (shown to the user as "assumed").
- Kazakh texts were not reviewed by a native speaker; Kazakh AI answers from a small model can
  contain mistakes.
- Opening-hours parser supports common formats only; others are shown raw as unverified.

## Risks for a real product

Data freshness, liability for unsafe or closed recommendations, LLM cost at scale, competition
with large map platforms, and the need for partnerships for events/ratings data.

## Business model (plausible, not validated)

- **B2G / city**: white-label "city walks" assistant for tourism portals or Smart City apps.
- **B2B**: widget for hotels, business centres, universities, malls ("what to do nearby").
- **Partners**: clearly labelled sponsored places/events — never mixed with organic results.

## Roadmap

1. Real walking routes via an open pedestrian routing engine instead of straight-line estimates
   (today: hand-off to external directions on click).
2. Whole-city dataset with scheduled refresh; add municipal open data and official event feeds.
3. Native-speaker review of Kazakh texts; reviewed name corrections with the OSM community.
4. Group rooms and invitations, several starting points, and more than three stops.
5. Decide on hybrid retrieval from measured results on real queries; turn local reports into
   reviewed OSM edits (with consent).
