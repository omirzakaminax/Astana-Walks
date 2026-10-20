# Submission checklist (matches «Формат сдачи» in the PDF)

| PDF item | What to submit | Status |
|---|---|---|
| Repository link (code optional) **or** archive with the prototype | GitHub repo (recommended) or the ZIP of this folder **with your real `data/pois.json` inside** | ⬜ |
| Presentation (PDF/slides), 5–7 min | `presentation/Astana_Walks_pitch.pdf` (and `.pptx`) — first replace `<N>` with your real place count | ⬜ |
| Document with test scenarios and limitations | `docs/TEST_SCENARIOS.md` (export to PDF if the form wants a file) — fill the "Observed (live)" column | ⬜ |
| Demo uploaded to YouTube, accessible by link | Unlisted video link (see `docs/DEMO_SCRIPT.md`) | ⬜ |

## Your remaining steps, in order (≈2.5–3.5 h)

1. ⬜ Unzip the new version over your folder (`Expand-Archive … -DestinationPath C:\hack -Force`); your
   `data\pois.json` is not in the ZIP and stays as it is.
2. ⬜ `scripts\collect_osm.py --all` (backs up the old file first) → then `scripts\enrich_wiki.py`.
3. ⬜ `scripts\data_report.py` → note the real counts (places, English-name sources, photos).
4. ⬜ `scripts\doctor.py --infer` and `python -m pytest -q` (or `-m unittest discover -s tests`).
5. ⬜ `eval\run_eval.py` and `eval\run_eval.py --live` → copy the measured numbers (with n) into the deck.
6. ⬜ Run the app, try the demo script once, fill the live column in `docs/TEST_SCENARIOS.md`.
7. ⬜ Replace `<N>`/`<…>` placeholders on the slides with your real numbers; re-export the PDF.
8. ⬜ Record the demo in daytime and upload it unlisted to YouTube.
9. ⬜ Push to GitHub:
   ```powershell
   git init
   git add .
   git commit -m "Astana Walks hackathon prototype"
   git branch -M main
   git remote add origin https://github.com/<you>/astana-walks.git
   git push -u origin main
   ```
   Check that `.env` and `.venv` are **not** in the repo (they are in `.gitignore`).
10. ⬜ Submit: repo link, PDF deck, test-scenario document, YouTube link.

## Optional ZIP instead of a repo (PowerShell)

```powershell
Compress-Archive -Path server.py,web,walks,scripts,tests,docs,presentation,data,README.md,requirements.txt,.env.example,.gitignore -DestinationPath astana-walks-submission.zip
```
