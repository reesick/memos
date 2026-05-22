"""
core/llm.py – Ollama LLM interface
All LLM calls go through Ollama. No external API dependencies.
"""

import os
import json
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")


class LLMError(Exception):
    """Raised when the LLM is unavailable or returns an error."""
    pass


def _call_ollama(prompt: str, temperature: float = 0.1) -> str:
    """Call Ollama HTTP API. Returns raw text response."""
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": temperature},
    }
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.post(url, json=payload)
            if response.status_code == 404:
                raise LLMError(
                    f"OLLAMA_MODEL_NOT_FOUND: Model '{OLLAMA_MODEL}' is not pulled. "
                    f"Fix: run `ollama pull {OLLAMA_MODEL}`"
                )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
    except httpx.ConnectError:
        raise LLMError("OLLAMA_UNAVAILABLE: Cannot connect to Ollama at " + OLLAMA_URL)
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"OLLAMA_ERROR: {str(e)}")


def call(prompt: str, temperature: float = 0.1) -> str:
    """Main LLM call. Uses Ollama. Raises LLMError if unavailable."""
    return _call_ollama(prompt, temperature)


def is_ollama_running() -> bool:
    """Health check: is the Ollama server process running?"""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{OLLAMA_URL}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


def is_model_available() -> bool:
    """Check if the configured OLLAMA_MODEL is pulled and ready."""
    if not is_ollama_running():
        return False
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code != 200:
                return False
            data = response.json()
            model_names = [m.get("name", "") for m in data.get("models", [])]
            base = OLLAMA_MODEL.split(":")[0]
            return any(
                OLLAMA_MODEL == name or name.startswith(base)
                for name in model_names
            )
    except Exception:
        return False


def call_json(prompt: str, temperature: float = 0.1) -> Optional[dict | list]:
    """
    Call LLM and parse response as JSON (array or object).
    Strips markdown code fences. Returns parsed data or None on failure.
    """
    raw = call(prompt, temperature).strip()

    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
