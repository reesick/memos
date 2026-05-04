"""
run.py – Entry point for MemoryOS
Checks Ollama health on startup, then starts FastAPI on localhost:8000.
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("memoryos")


def check_ollama():
    from core.llm import (
        is_ollama_running, is_openai_compat_available,
        LLM_PROVIDER, CLAUDE_API_KEY, OPENAI_COMPAT_KEY, OPENAI_COMPAT_URL, OPENAI_COMPAT_MODEL,
    )

    if LLM_PROVIDER == "openai_compat":
        if not OPENAI_COMPAT_KEY:
            logger.error(
                "✗  LLM_PROVIDER=openai_compat but OPENAI_COMPAT_KEY is not set.\n"
                "   Add OPENAI_COMPAT_KEY=<your-key> to .env\n\n   Exiting."
            )
            sys.exit(1)
        logger.info(f"✓  OpenAI-compatible provider ready: {OPENAI_COMPAT_URL} | model={OPENAI_COMPAT_MODEL}")

    elif LLM_PROVIDER == "claude":
        if not CLAUDE_API_KEY or CLAUDE_API_KEY == "sk-ant-xxx":
            logger.error(
                "✗  LLM_PROVIDER=claude but CLAUDE_API_KEY is not set.\n"
                "   Add CLAUDE_API_KEY=<your-key> to .env\n\n   Exiting."
            )
            sys.exit(1)
        logger.info("✓  Claude API configured.")

    elif LLM_PROVIDER == "ollama":
        if not is_ollama_running():
            if OPENAI_COMPAT_KEY:
                logger.warning("⚠  Ollama not running. Auto-fallback to OpenAI-compatible provider.")
            elif CLAUDE_API_KEY and CLAUDE_API_KEY != "sk-ant-xxx":
                logger.warning("⚠  Ollama not running. Auto-fallback to Claude API.")
            else:
                logger.error(
                    "✗  Ollama is not running and no fallback LLM is configured.\n"
                    "   Options:\n"
                    "     1. ollama pull llama3.1:7b && ollama serve\n"
                    "     2. Set LLM_PROVIDER=openai_compat + OPENAI_COMPAT_KEY in .env\n"
                    "     3. Set LLM_PROVIDER=claude + CLAUDE_API_KEY in .env\n\n   Exiting."
                )
                sys.exit(1)
        else:
            logger.info("✓  Ollama is running and ready.")


def main():
    logger.info("=" * 60)
    logger.info("  MemoryOS v1.0 – Starting up")
    logger.info("=" * 60)

    # Step 1: Check LLM availability
    check_ollama()

    # Step 2: Pre-initialize stores (eager load so first request is fast)
    import core.engine as engine
    engine._init_stores()
    logger.info("✓  All stores initialized.")

    # Step 3: Start API server
    host = os.getenv("API_HOST", "localhost")
    port = int(os.getenv("API_PORT", "8000"))

    logger.info(f"✓  Starting API server at http://{host}:{port}")
    logger.info(f"   API Docs: http://{host}:{port}/docs")
    logger.info("=" * 60)

    import uvicorn
    uvicorn.run("api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
