# Demo video script (≈3 minutes) + recording and YouTube steps

Show the **real running system on real collected data**. Never record with the synthetic fixture
(red banner) or a mocked model.

## Before recording (10 min)

1. `ollama run qwen3:4b-instruct "hi"` (or your model): warms it up so the first answer is fast.
   Record in the daytime if you can: late in the evening many places are closed and the planner will say so.
2. `.venv\Scripts\python server.py`; browser zoom 110–125 %; close other tabs.
3. Do one dry run of each scenario below; if a result is weak, it is fine to show it honestly.
4. Turn off notifications (Windows: Focus assist / Do not disturb).

## Script (≈4 minutes, strongest features first)

Real numbers from your laptop (2026-10-20): 502 places; 95 of 478 named places have a sourced English
name. Update them if you re-collect.

| Time | On screen | Say (translate to RU/KK if you present in that language) |
|---|---|---|
| 0:00–0:15 | Start screen, English | "Astana Walks: a walking assistant for the Smart City case. Real nearby places that fit your time — and it says what it doesn't know." |
| 0:15–0:35 | Terminal: `collect_osm.py --all` + `data_report.py` output (pre-run) | "Collected automatically from OpenStreetMap: 502 places in three areas plus sights across the city. Every name keeps its source: only 95 of 478 named places have an English name in OpenStreetMap, and we don't invent the rest." |
| 0:35–1:00 | Start box: type "baiterek", then "Хан Шатыр", then "AITU" (if in your data) | "Search the start in any language or spelling. On the English page, a place with no English name in the data keeps its real name with an English type — e.g. 'Атырау көпірі — Attraction, ≈ Atyrau Bridge, descriptive translation' — instead of inventing 'Atyrau kopiri'." |
| 1:00–1:40 | Start = a central place. Request "coffee, then a short walk, no museums", 60 min | "Negations and order are understood. Code filters by time, opening hours at arrival and type; the model only chooses among these places and explains. Each card shows source facts, calculated facts ('≈ 14 min left after this stop') and the AI text, labelled separately." |
| 1:40–2:05 | More options: "Be back by" in 1 hour + outdoor limit 10 min; ask again | "A deadline and 'don't let me freeze' change the plan: the limits are hard, the plan is recalculated, and nothing is relaxed silently." If nothing fits, show the reasons and "Allow 20 min outdoors (now 10)": "Each change is explicit." |
| 2:05–2:25 | "Other ways to do this walk": press "Less walking" | "Alternatives from the same places under the same limits — I pick one and it becomes the plan." |
| 2:25–2:50 | "Start this walk" → on card 1 "I'm here / done" → "Recalculate remaining walk" | "During the walk I mark where I am; the rest is recalculated from here with the time I have left, and the way back still ends at my original start. Nothing is tracked in the background." |
| 2:50–3:05 | Card: "Walking directions ↗" (open, then close the tab) | "For street directions I hand over to Google Maps or OpenStreetMap — only when I click. Our times are estimates, not a street route." |
| 3:05–3:20 | Type "I want to see Baiterek" from Mega Silk Way with 60 min, then "coffee near Baiterek" | "A named place that doesn't fit is explained — 'too far for your time' with the estimated walk. And if the text names a different start, it asks once instead of planning from the wrong place." |
| 3:20–3:35 | Copy plan / Save plan; tick one Bingo mission; "Report a problem" (show the form, cancel) | "Take it offline; report a wrong name locally — nothing is published automatically." |
| 3:35–3:50 (optional, +20 s) | Scroll down to "Place of the day" and "Astana in photos"; tap a photo; switch to "Guess the place" and answer one | "Every photo is a free-licensed Wikimedia photo of a place in our data, credited. Tap one and it tells you what it is — or play 'Guess the place'. The place of the day is picked by date, not a ranking. 'Start my walk here' turns it into a plan." |
| 3:35–3:50 | Switch Қаз → Рус → Eng; dark theme; low-vision mode | "Three languages switch instantly, names from sources; dark theme and low-vision mode." |
| 3:50–4:00 | "How this answer was built": evidence, timings, retrieval mode; footer | "The trace shows the evidence the model saw and measured times. The model never receives my coordinates." |

Optional: stop Ollama and press the button → the honest error plus "search results only" list.

## Recording on Windows (free)

- **Xbox Game Bar**: `Win + Alt + R` starts/stops recording the active window (saved in
  `Videos\Captures`). Microphone: `Win + Alt + M`.
- Or **OBS Studio** (free, `winget install -e --id OBSProject.OBSStudio`): Sources → Window
  Capture (browser) + Audio input; Settings → Output → MP4; Start Recording.
- Or Windows **Snipping Tool** → Record (Windows 11).

## Upload to YouTube and submit the link

1. youtube.com → sign in → **Create → Upload video** → select the MP4.
2. Title: "Astana Walks — Smart City walking assistant (Build with AI hackathon)".
3. Description: 2 lines + repo link + "Data © OpenStreetMap contributors (ODbL)".
4. Audience: "No, it's not made for kids".
5. Visibility: **Unlisted** (anyone with the link can watch) — the brief requires access by link.
   Public also works.
6. Wait for processing, open the link in a private window to confirm it plays, then put the link
   in the submission form, the README and the last slide.
