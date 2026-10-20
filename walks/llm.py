"""LLM providers. Default: local Ollama (free, nothing leaves your laptop).
Optional: Google Gemini API (only if GEMINI_API_KEY and GEMINI_MODEL are set).

Both return the raw model text; walks.pipeline parses and validates it.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests

from . import config


class LLMError(RuntimeError):
    """Raised with an English message plus a stable `code` the UI translates.

    Codes: ollama_unreachable, timeout, model_missing, http_error, bad_response,
           gemini_not_configured, quota, network, busy
    """

    def __init__(self, message: str, code: str = "http_error", **params):
        super().__init__(message)
        self.code = code
        self.params = params


@dataclass
class LLMReply:
    text: str
    provider: str
    model: str
    seconds: float
    prompt_tokens: int | None = None   # Ollama prompt_eval_count
    output_tokens: int | None = None   # Ollama eval_count
    done_reason: str | None = None     # "stop" or "length" (hit LLM_NUM_PREDICT)


def provider_name() -> str:
    return config.LLM_PROVIDER if config.LLM_PROVIDER in ("ollama", "gemini") else "ollama"


_slots = threading.BoundedSemaphore(max(1, config.LLM_MAX_CONCURRENT))


def generate(system: str, user: str, schema: dict | None = None) -> LLMReply:
    """One model call. `schema` (JSON Schema) is passed to Ollama's structured outputs; the reply
    is still validated by walks.pipeline. Concurrent requests wait for a free slot (bounded)."""
    if not _slots.acquire(timeout=config.LLM_TIMEOUT_S):
        raise LLMError("The local model is busy with other requests. Try again in a moment.", "busy")
    try:
        if provider_name() == "gemini":
            return _gemini(system, user)
        return _ollama(system, user, schema)
    finally:
        _slots.release()


THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1", "magistral")


def is_thinking_model(name: str) -> bool:
    n = name.lower()
    # "-instruct" variants (e.g. qwen3-vl:4b-instruct) never think: send nothing extra.
    return n.startswith(THINKING_MODEL_PREFIXES) and "instruct" not in n


def _ollama(system: str, user: str, schema: dict | None = None) -> LLMReply:
    url = f"{config.OLLAMA_URL}/api/chat"
    body = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        # Structured outputs (Ollama >= 0.5): a JSON Schema constrains the reply. Older versions: "json".
        "format": schema or "json",
        "options": {"temperature": config.LLM_TEMPERATURE, "num_ctx": config.LLM_NUM_CTX,
                    "num_predict": config.LLM_NUM_PREDICT},
    }
    if is_thinking_model(config.OLLAMA_MODEL):
        # Qwen3 & co. "think" by default: slower and can wrap the JSON in <think> text.
        body["think"] = False
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
        if r.status_code == 400 and "think" in body and "think" in r.text.lower():
            # Older Ollama versions do not know the "think" option: retry without it.
            body.pop("think")
            body["messages"][1]["content"] = user + "\n/no_think"
            r = requests.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
        if r.status_code in (400, 500) and isinstance(body["format"], dict) and "format" in r.text.lower():
            body["format"] = "json"  # this Ollama version does not accept a schema
            r = requests.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
    except requests.exceptions.ConnectionError:
        raise LLMError(f"Cannot reach Ollama at {config.OLLAMA_URL}. Is it running? "
                       "Open the Ollama app or run `ollama serve` in another terminal.",
                       "ollama_unreachable", url=config.OLLAMA_URL) from None
    except requests.exceptions.Timeout:
        raise LLMError(f"Ollama did not answer within {config.LLM_TIMEOUT_S:.0f} s "
                       f"(prompt ≈{len(system) + len(user)} characters, output capped at {config.LLM_NUM_PREDICT} tokens). "
                       "The first request also loads the model; try again, or use a smaller model.",
                       "timeout", seconds=int(config.LLM_TIMEOUT_S)) from None
    if r.status_code == 404:
        raise LLMError(f"Ollama model '{config.OLLAMA_MODEL}' is not installed. "
                       f"Run: ollama pull {config.OLLAMA_MODEL}", "model_missing", model=config.OLLAMA_MODEL)
    if r.status_code != 200:
        raise LLMError(f"Ollama returned HTTP {r.status_code}: {r.text[:200]}", "http_error", status=r.status_code)
    try:
        data = r.json()
        content = data["message"]["content"]
    except (ValueError, KeyError, TypeError):
        raise LLMError("Ollama returned an unexpected response format.", "bad_response") from None
    return LLMReply(content, "ollama", config.OLLAMA_MODEL, time.perf_counter() - t0,
                    prompt_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
                    done_reason=data.get("done_reason"))


def _gemini(system: str, user: str) -> LLMReply:
    if not config.GEMINI_API_KEY or not config.GEMINI_MODEL:
        raise LLMError("Gemini is selected but GEMINI_API_KEY or GEMINI_MODEL is not set. "
                       "Set both in .env (local) or in hosting secrets, or switch LLM_PROVIDER=ollama.",
                       "gemini_not_configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": config.LLM_TEMPERATURE, "responseMimeType": "application/json"},
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=body, timeout=config.LLM_TIMEOUT_S,
                          headers={"x-goog-api-key": config.GEMINI_API_KEY})
    except requests.exceptions.RequestException as exc:
        raise LLMError(f"Could not reach the Gemini API: {type(exc).__name__}", "network") from None
    if r.status_code == 429:
        raise LLMError("Gemini free-tier quota reached (HTTP 429). Wait and retry, or use local Ollama.", "quota")
    if r.status_code != 200:
        # Never echo the key; the response body does not contain it.
        raise LLMError(f"Gemini returned HTTP {r.status_code}: {r.text[:200]}", "http_error", status=r.status_code)
    try:
        content = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("Gemini returned no usable text (possibly blocked or empty).", "bad_response") from None
    return LLMReply(content, "gemini", config.GEMINI_MODEL, time.perf_counter() - t0)


def check_ollama() -> tuple[bool, str]:
    """Quick health check used by scripts/check_llm.py."""
    st = status()
    return st["ok"], st["detail"]


def status() -> dict:
    """Provider status for the UI: {ok, code, provider, model, detail}."""
    if provider_name() == "gemini":
        ok = bool(config.GEMINI_API_KEY and config.GEMINI_MODEL)
        return {"ok": ok, "code": "ready" if ok else "gemini_not_configured", "provider": "gemini",
                "model": config.GEMINI_MODEL, "detail": "Gemini API" if ok else "GEMINI_API_KEY / GEMINI_MODEL not set"}
    base = {"provider": "ollama", "model": config.OLLAMA_MODEL}
    try:
        r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return {**base, "ok": False, "code": "ollama_unreachable", "detail": f"Ollama not reachable at {config.OLLAMA_URL}"}
    if not any(n == config.OLLAMA_MODEL or n.startswith(config.OLLAMA_MODEL + ":") for n in names):
        return {**base, "ok": False, "code": "model_missing",
                "detail": f"Ollama is running but model '{config.OLLAMA_MODEL}' is missing (ollama pull {config.OLLAMA_MODEL})"}
    return {**base, "ok": True, "code": "ready", "detail": f"Ollama ready: {config.OLLAMA_MODEL}"}
