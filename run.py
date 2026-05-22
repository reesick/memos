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
    from core.llm import is_ollama_running, OLLAMA_MODEL
    if not is_ollama_running():
        logger.error(
            "✗  Ollama is not running.\n"
            "   MemoryOS requires Ollama to function.\n"
            "   Fix:\n"
            f"     1. Install Ollama: https://ollama.com\n"
            f"     2. Run: ollama pull {OLLAMA_MODEL} && ollama serve\n"
            "\n   Exiting."
        )
        sys.exit(1)
    else:
        logger.info(f"✓  Ollama is running. Model: {OLLAMA_MODEL}")


def main():
    logger.info("=" * 60)
    logger.info("  MemoryOS v1.0 – Starting up")
    logger.info("=" * 60)

    check_ollama()

    import core.engine as engine
    engine._init_stores()
    logger.info("✓  All stores initialized.")

    host = os.getenv("API_HOST", "localhost")
    port = int(os.getenv("API_PORT", "8000"))

    logger.info(f"✓  Starting API server at http://{host}:{port}")
    logger.info(f"   API Docs: http://{host}:{port}/docs")
    logger.info("=" * 60)

    import uvicorn
    uvicorn.run("api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
