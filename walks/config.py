"""Central configuration. Values come from environment variables (or a local .env file).

Nothing secret is hard-coded here. Copy .env.example to .env to change settings.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines) so we do not need python-dotenv.

    Existing environment variables always win over the file.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")



# --- Data -------------------------------------------------------------------
DATA_PATH = Path(os.environ.get("WALKS_DATA_PATH", PROJECT_ROOT / "data" / "pois.json"))
# Reviewed name corrections keyed by POI ID (each needs a source URL and review date).
NAME_OVERRIDES_PATH = Path(os.environ.get("WALKS_NAME_OVERRIDES", PROJECT_ROOT / "data" / "name_overrides.json"))
# Cache for optional semantic-search embeddings and Wikimedia answers (safe to delete).
CACHE_DIR = Path(os.environ.get("WALKS_CACHE_DIR", PROJECT_ROOT / "data" / "cache"))

# --- Time -------------------------------------------------------------------
# Astana uses UTC+5 all year (Kazakhstan unified on UTC+5 in March 2024).
# A fixed offset avoids needing the tzdata package on Windows.
ASTANA_TZ = timezone(timedelta(hours=5), name="Astana (UTC+5)")

# --- Walking model (honest, approximate) ------------------------------------
WALK_SPEED_M_PER_MIN = float(os.environ.get("WALK_SPEED_M_PER_MIN", "75"))  # ~4.5 km/h
# Straight-line distance underestimates real streets; multiply to approximate a route.
ROUTE_DETOUR_FACTOR = float(os.environ.get("ROUTE_DETOUR_FACTOR", "1.3"))

# --- Retrieval --------------------------------------------------------------
CANDIDATES_FOR_LLM = int(os.environ.get("CANDIDATES_FOR_LLM", "6"))
# "lexical" (default: BM25 + category + proximity) or "hybrid" (adds a local multilingual embedding
# model, fused with reciprocal-rank fusion). Hybrid needs: pip install -r requirements-semantic.txt
RETRIEVAL_MODE = os.environ.get("RETRIEVAL_MODE", "lexical").strip().lower()
SEMANTIC_MODEL = os.environ.get("SEMANTIC_MODEL", "intfloat/multilingual-e5-small").strip()
MAX_RECOMMENDATIONS = 3

# --- LLM providers ----------------------------------------------------------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()  # "ollama" or "gemini"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "120"))
# Hard cap on generated tokens: a valid answer (≤3 places, 2 short sentences each) needs ~150–400
# tokens even in Kazakh. Without a cap a small model can repeat itself until the timeout.
LLM_NUM_PREDICT = int(os.environ.get("LLM_NUM_PREDICT", "700"))
# Context window. Kazakh text needs ~2x the tokens of English; prompts are trimmed to fit (pipeline).
LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "6144"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.1"))
LLM_MAX_CONCURRENT = int(os.environ.get("LLM_MAX_CONCURRENT", "1"))  # one local model call at a time

# --- Weather (Open-Meteo, free, no key) -----------------------------------------
WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "1").strip() not in ("0", "false", "no")
WEATHER_TIMEOUT_S = float(os.environ.get("WEATHER_TIMEOUT_S", "4"))

# --- Web server ---------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8501"))

# Optional. Leave empty to disable. Never commit a real key.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Model IDs change often: copy a free-tier model ID shown in Google AI Studio.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip()
