"""
core/llm.py – Unified LLM interface
Supports Ollama (local, default) and Claude API (fallback).
NOTHING else in the engine calls Ollama or Claude directly – always via this module.

Root fixes applied:
- 404 from Ollama now correctly identified as MODEL_NOT_FOUND (not pulled), not generic error
- Fallback to Claude triggered on both UNAVAILABLE and MODEL_NOT_FOUND
- is_model_available() checks model list from /api/tags for precise test skip guards
- call_json() improved: tries both array and object JSON parsing with boundary detection
"""

import os
import json
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:7b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")


class LLMError(Exception):
    """Raised when no LLM is available."""
    pass


def _call_ollama(prompt: str, temperature: float = 0.1) -> str:
    """Call Ollama HTTP API. Returns raw text response."""
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)

            # Root fix: 404 = model not pulled. Give actionable message.
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
        raise  # Re-raise our typed errors unchanged
    except Exception as e:
        raise LLMError(f"OLLAMA_ERROR: {str(e)}")


def _call_claude(prompt: str, temperature: float = 0.1) -> str:
    """Call Claude API via Anthropic SDK. Returns raw text response."""
    if not CLAUDE_API_KEY or CLAUDE_API_KEY == "sk-ant-xxx":
        raise LLMError("CLAUDE_UNAVAILABLE: No CLAUDE_API_KEY set in .env")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        raise LLMError(f"CLAUDE_ERROR: {str(e)}")


def call(prompt: str, temperature: float = 0.1) -> str:
    """
    Main LLM call. Uses LLM_PROVIDER from .env.
    Auto-fallback: if Ollama is unavailable OR model not found, tries Claude.
    Raises LLMError if neither is available.
    """
    if LLM_PROVIDER == "ollama":
        try:
            return _call_ollama(prompt, temperature)
        except LLMError as e:
            err = str(e)
            # Root fix: trigger fallback on UNAVAILABLE *or* MODEL_NOT_FOUND
            can_fallback = (
                ("UNAVAILABLE" in err or "MODEL_NOT_FOUND" in err)
                and CLAUDE_API_KEY
                and CLAUDE_API_KEY != "sk-ant-xxx"
            )
            if can_fallback:
                return _call_claude(prompt, temperature)
            raise

    elif LLM_PROVIDER == "claude":
        try:
            return _call_claude(prompt, temperature)
        except LLMError:
            try:
                return _call_ollama(prompt, temperature)
            except LLMError:
                raise LLMError("LLM_UNAVAILABLE: Both Claude and Ollama failed.")
    else:
        raise LLMError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


def is_ollama_running() -> bool:
    """Health check: is the Ollama server process running? (Not the model.)"""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{OLLAMA_URL}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


def is_model_available() -> bool:
    """
    Precise check: is the configured OLLAMA_MODEL actually pulled and listed?
    Uses /api/tags which returns all downloaded models.
    Used for test skip guards – more accurate than is_ollama_running().
    """
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
            # Match exact name OR prefix (e.g. "llama3.1:7b" matches "llama3.1:7b-instruct-q4")
            return any(
                OLLAMA_MODEL == name or name.startswith(base)
                for name in model_names
            )
    except Exception:
        return False


def call_json(prompt: str, temperature: float = 0.1) -> Optional[dict | list]:
    """
    Call LLM and parse response as JSON (array or object).
    Strips markdown code fences. Tries both [] and {} boundaries.
    Returns parsed data or None on failure.
    """
    raw = call(prompt, temperature)
    raw = raw.strip()

    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

    # Try JSON array first, then object
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    # Last attempt: raw string
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
