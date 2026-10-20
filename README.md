# Astana Walks: a grounded city-walk assistant

> Submission status, evidence and remaining steps: **[FINAL_AUDIT.md](FINAL_AUDIT.md)**.

Hackathon "Build with AI", **Case 1: НИЦ Smart City** (AI walking assistant for Astana).

Tell it where you are, how much time you have and what you'd like. It retrieves real places from its
own OpenStreetMap dataset, filters them **in code** by distance, time, type, opening hours, weather
and your "no …" wishes, and asks a **local** LLM (Ollama) to pick 1–3 and explain why. Every card
shows the source link, the place's name *with its provenance*, a straight-line distance, an
approximate walking time, a calculated "how it fits" list and what is known, or unknown, about
opening hours.

- Interface in **Kazakh, Russian and English**; requests are understood in all three, including
  negations ("no cafes", "без кафе", "кафесіз") and "coffee, then a walk".
- **Place names you can trust**: a sourced name in your language when one exists (OSM `name:xx`,
  a verified Wikidata label or a reviewed correction); otherwise the original name with a
  translated place type. Transliteration is only a search alias and a labelled pronunciation aid.
  See `docs/NAMING.md`.
- **Searchable start picker** (any language, Latin spelling, initials) or **a point on the map**;
  typed coordinates and browser geolocation still work.
- **More options**: walking pace, "be back by" time with a buffer, an outdoor-time limit, group mode
  for 2–5 people, and source-based filters (known opening hours, OSM wheelchair tag).
- **On every plan**: replace / visited / closed / remove, 2–3 **plan styles** (less walking, more
  variety, less time outdoors), **walking directions** handed to Google Maps or OpenStreetMap on
  click, an **"I'm here" active walk** that recalculates the rest, **report a name/data problem**,
  copy or save an offline plan, **Surprise me** and **City Bingo**.
- **Light and dark themes**, plus a **low-vision mode** and read-aloud on each card.
- One **canonical itinerary** drives cards, map numbers, timeline, exports, Bingo and plan styles.

```
request ─► understand (KK/RU/EN: intents, negations, named places, time) ─► ask once if the start is ambiguous
        ─► filter in code (distance+time, type, "no …", hours, outdoor cap, source filters)
        ─► rank (BM25 + type fit + proximity [+ optional local embeddings, RRF]) ─► top-6 evidence
        ─► LLM (JSON Schema, evidence IDs only, ≤1 repair) ─► remove unsupported sentences
        ─► canonical itinerary (+ alternative styles) ─► cards with sources and calculated facts
```

Cost: **0 KZT**. Python, OpenStreetMap, Open-Meteo, Wikimedia and Ollama are free; no account, card
or cloud credits are needed. The web server uses only Python's standard library (plus `requests`).

---

## 1. One-time setup (Windows 11, PowerShell)

Open **PowerShell** (the prompt starts with `PS`) in the project folder. All commands call
`.venv\Scripts\python` directly, so you never need to "activate" the venv.

```powershell
# 1) Python 3.12: if `py -3.12` gives "Access is denied" (Microsoft Store Python), use the python.org build:
winget install -e --id Python.Python.3.12 --scope user
#    then, in a NEW PowerShell window, from the project folder:
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv

# 2) Ollama + a model
winget install -e --id Ollama.Ollama
ollama pull qwen3:4b-instruct

# 3) Project packages and settings
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env          # set OLLAMA_MODEL to the exact name from `ollama list`
$env:PYTHONUTF8 = "1" # correct Cyrillic in console output (per session)
```

**Which model:** `qwen3:4b-instruct` (2.5 GB, good Russian/Kazakh, no "thinking" delay) is the
recommended choice. On a weak laptop use `qwen3:1.7b` or `qwen2.5:1.5b`. Ollama ≥ 0.5 receives a JSON
Schema (structured outputs); older versions fall back to plain JSON mode automatically.

## 2. Collect (or update) the real dataset

```powershell
.venv\Scripts\python scripts\collect_osm.py --all
```

`--all` runs four polite Overpass queries and **merges** them into `data\pois.json` (never replaces
it): the EXPO/AITU area, the centre, the right bank, and a citywide pass for sights. It keeps all
name variants with their language tags (`name:kk/ru/en`, `official_name`, `alt_name`, …), then adds
**photos and short descriptions** from Wikimedia Commons / Wikipedia / Wikidata. Before saving, the
old file is copied to `data\backups\` (last 3 kept). Wikimedia answers are cached for 30 days in
`data\cache\` (`scripts\enrich_wiki.py --refresh` ignores the cache).

**If you already collected data with an older version**: nothing to migrate by hand. On load, names
are rebuilt from each record's own OSM tags; names guessed by older versions become unverified
search aliases (never shown as a localized name). To restore full provenance and run the new
Wikidata identity check, re-run:

```powershell
.venv\Scripts\python scripts\collect_osm.py --all          # backs up the old file first
.venv\Scripts\python scripts\data_report.py                # writes data\reports\data_quality.md
```

The report lists real counts: places per area and category, opening-hours coverage, wheelchair tags,
merges with reasons, media, and every place without a sourced English name. To fix an important
name, add a reviewed entry (ID + source URL + date) to `data\name_overrides.json` (`docs/NAMING.md`).

## 3. Check everything (diagnostic)

```powershell
.venv\Scripts\python scripts\doctor.py --infer
```

PASS/WARN/FAIL for Python, packages, dataset validity, name sources, media, model status and the
retrieval mode, then two **real** model calls with measured times (the first includes loading the
model). `scripts\check_llm.py` still prints a full RAG answer with the chosen places.

## 4. Run the tests

```powershell
.venv\Scripts\python -m pytest -q          # or: .venv\Scripts\python -m unittest discover -s tests
```

179 tests (one runs only if Node.js is installed). They use **synthetic places**, a **fake model**,
a **fixed clock** and **local mock servers**: they check planning, names, grounding, the API and
error handling, not real data quality or the real model.

Browser check (optional; needs `pip install playwright` and `python -m playwright install chromium`):

```powershell
.venv\Scripts\python tests\e2e\mock_ollama.py 11999                     # window 1: FAKE model
$env:WALKS_DATA_PATH="tests\e2e\e2e_pois.json"; $env:OLLAMA_URL="http://127.0.0.1:11999"; $env:OLLAMA_MODEL="qwen3:4b-instruct"; $env:WEATHER_ENABLED="0"
.venv\Scripts\python server.py --port 8765 --no-browser                 # window 2
.venv\Scripts\python tests\e2e\browser_check.py http://localhost:8765 shots   # window 3
```

## 5. Evaluate (reproducible, measured)

```powershell
.venv\Scripts\python eval\run_eval.py            # 29 KK/RU/EN queries: retrieval, constraints, names (no model)
.venv\Scripts\python eval\run_eval.py --live     # + your real model: valid IDs, JSON errors, removed claims, latency
```

Results go to `eval\results\`. Labels are category-level; for POI-level Hit@5, fill the `relevant`
column of `eval\results\*-to_label.csv` for your data snapshot and save it as `eval\labels.csv`.
See `docs/EVALUATION.md`.

## 6. Launch the app

```powershell
.venv\Scripts\python server.py
```

The browser opens `http://localhost:8501`. Choose the language, theme and low-vision mode in the top
right. Type in the start box (e.g. "baiterek", "Хан Шатыр", "AITU") or choose **Point on the map**,
set the minutes, pick interests or type a request, and press the button. Stop with `Ctrl+C`.

Example requests:

- `I'm near EXPO and have 45 minutes. Where can I walk?`
- `Хочу тихое место с кофе и розеткой рядом` (quietness/sockets reported as unknown)
- `coffee, then a short walk, no museums`
- `кофе рядом с Байтереком` while the start is elsewhere (the app asks once which start to use)

Internet is needed for map tiles, web fonts, weather, photos and external directions; without it
the app still plans: system fonts, a note instead of the map, no weather tag, no photos.

## 7. Optional: semantic (hybrid) retrieval

Not needed for the demo, and **not the default**: we have no evidence yet that it beats the lexical
ranking on our queries. To try it (≈ 1 GB download incl. CPU PyTorch and the model):

```powershell
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r requirements-semantic.txt
# in .env: RETRIEVAL_MODE=hybrid
.venv\Scripts\python eval\run_eval.py --mode both     # compare lexical vs hybrid on the same queries
```

If the model cannot load, the app uses lexical retrieval and says so in "How this answer was built".

## 8. Optional: Gemini instead of Ollama

In `.env`: `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=…`, `GEMINI_MODEL=<a free-tier model ID from AI
Studio>`. With Gemini, the request text and retrieved place evidence go to Google; your coordinates
do not. Never commit `.env`. See `docs/DEPLOYMENT.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `py ... Access is denied` | Microsoft Store Python. Install python.org Python (step 1) and create the venv with the full path. |
| `'Copy-Item' is not recognized` | You are in cmd. Use `copy`, or type `powershell` first. |
| Footer says "Ollama is not running" | Start the Ollama app or run `ollama serve`, then reload the page. |
| "Model … is not installed" | `ollama pull <name>` and make `OLLAMA_MODEL` match `ollama list` exactly. |
| First answer slow or timeout | The first call loads the model. Retry. Answers are capped at `LLM_NUM_PREDICT=700` tokens so a model cannot run on until the timeout; the page then offers **Try the model again** or **Plan without AI text** (chosen by the app, same limits, clearly labelled). Check `scripts\doctor.py --infer` for the measured time. |
| Collector: HTTP 429 / 504 / timeout | Overpass is busy. Wait 2–5 minutes and retry; the script already tries 3 servers. |
| A place shows its Kazakh/Russian name on the English page | Correct behaviour when no sourced English name exists: the card says so and shows the type. Add a reviewed override if you can source one. |
| Cyrillic shows as `?` in the console | `$env:PYTHONUTF8 = "1"` |
| Port 8501 busy | `.venv\Scripts\python server.py --port 8502` |
| UI test without real data | `$env:WALKS_DATA_PATH = "tests\fixtures\synthetic_pois.json"`: a red "test data" banner appears. Never record the demo like this. |

## Project layout

```
server.py                  local web server + JSON API: /api/meta, /api/places, /api/recommend, /api/replace, /api/replan
web/index.html             page skeleton
web/assets/styles.css      design tokens (palette), light/dark/low-vision themes
web/assets/i18n*.js        interface texts: Kazakh, Russian, English
web/assets/plan.js         pure helpers: names from the API, export text/HTML, directions URLs, Bingo (tested in Node)
web/assets/app.js          interface logic (picker, plan, styles, active walk, reports, map)
walks/names.py             provenance-aware place names (the only naming policy; used by API and exports)
walks/search.py            search by any name/alias/spelling; places named in free text
walks/dedup.py             conservative duplicate merging with recorded reasons
walks/data.py              dataset validation + name normalisation on load
walks/report.py            data-quality and naming audit
walks/osm_collect.py       Overpass query, normalisation, merge, backup, atomic save
walks/enrich.py            Wikimedia photos/descriptions with identity check, licence check, cache
walks/text.py              KK/RU/EN intents, negations, sequence words, time parsing, unsupported asks
walks/constraints.py       validation + precedence: time, deadline, group, pace, outdoor, filters, exclusions
walks/retrieval.py         hard filters + BM25 ranking (+ optional semantic RRF) + diversity
walks/semantic.py          optional local multilingual embeddings (RETRIEVAL_MODE=hybrid)
walks/itinerary.py         the canonical plan: order, durations, legs, return point, hours at arrival, outdoor minutes
walks/styles.py            alternative plan styles from the same eligible places
walks/grounding.py         clause-level claim checking against evidence fields
walks/llm.py               Ollama (structured outputs) / Gemini clients, bounded concurrency
walks/pipeline.py          evidence, prompts, repair, validation, coverage, fit facts, JSON for the UI
scripts/                   collect_osm, enrich_wiki, data_report, doctor, check_llm
eval/                      evaluation queries, runner and measured results
tests/                     unit + API tests (synthetic fixtures, fake model) and the browser check
docs/                      concept, naming, evaluation, features, test scenarios, checklists, demo script
presentation/              pitch deck (PPTX + PDF)
```

Data © OpenStreetMap contributors, ODbL 1.0. Photos: Wikimedia Commons (licence per file).
Descriptions: Wikipedia (CC BY-SA) / Wikidata (CC0). Weather: Open-Meteo, CC BY 4.0.
