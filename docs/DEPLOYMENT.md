# Deployment and cost

## A. Local launch: the baseline (0 KZT)

Everything in `README.md` runs on your laptop: Python, `server.py`, the collected `data/pois.json`
and a local Ollama model. No card, no account, no cloud credits. **Use this for the demo video
and a live pitch.** The hackathon brief requires a prototype (repo or archive) and a YouTube demo,
not a public website.

Internet is only used, from your browser and server, for: OpenStreetMap map tiles, Google web
fonts, and Open-Meteo weather. All three are free and optional; the app works without them.

## B. Optional public URL

### Why "public host + Ollama on my laptop" does not work

A hosted app runs on someone else's server. `http://localhost:11434` there means *that* server,
not your laptop, so it cannot reach the Ollama on your computer. Don't present such a deployment
as working, and don't expose your laptop to the internet for judges: it can sleep, lose Wi-Fi or
be overloaded by several requests, and it is a security risk.

### What could work, if you want it

Any free Python web host that can run `python server.py --host 0.0.0.0 --port <PORT>`
(for example Hugging Face Spaces or Render, check their current free terms yourself), with:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=<set as a secret in the host's settings, never in the repo>
GEMINI_MODEL=<a model ID your Google AI Studio project lists as free>
WEATHER_ENABLED=1
```

and `data/pois.json` committed to the repo. Things you must verify yourself (they change, and I
could not confirm them for you): the host's free tier and whether it needs a card, Gemini free-tier
availability and limits for your account (Google's terms require 18+), and that free-tier prompts
may be used by Google to improve its products.

Privacy note for a hosted version: the request text and the retrieved place evidence go to
Google; the user's coordinates go to your hosted server (to compute distances) but are not sent
to Gemini and are not logged. Say this in the pitch if you show it.

If any of this is not free for you, skip it: the local launch plus the video meets the brief.
