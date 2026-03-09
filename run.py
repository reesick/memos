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
    from core.llm import is_ollama_running, LLM_PROVIDER, CLAUDE_API_KEY
    if LLM_PROVIDER == "ollama":
        if not is_ollama_running():
            if CLAUDE_API_KEY and CLAUDE_API_KEY != "sk-ant-xxx":
                logger.warning(
                    "⚠  Ollama is not running. Auto-fallback to Claude API activated.\n"
                    "   To use Ollama: run `ollama serve` and `ollama pull llama3.1:7b`"
                )
            else:
                logger.error(
                    "✗  Ollama is not running and no CLAUDE_API_KEY is set.\n"
                    "   MemoryOS requires at least one LLM to function.\n"
                    "   Options:\n"
                    "     1. Install Ollama: https://ollama.com\n"
                    "        Then: ollama pull llama3.1:7b && ollama serve\n"
                    "     2. Set CLAUDE_API_KEY in .env and set LLM_PROVIDER=claude\n"
                    "\n   Exiting."
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
