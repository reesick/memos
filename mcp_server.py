"""
mcp_server.py – MemoryOS MCP server
Exposes memory_add, memory_search, memory_augment, memory_delete, memory_graph
as MCP tools for Claude Code, Cursor, and Windsurf.

Run standalone:
    python mcp_server.py

Configure in Claude Code (.claude/mcp.json):
    {
      "mcpServers": {
        "memoryos": {
          "command": "python",
          "args": ["mcp_server.py"],
          "cwd": "/path/to/memos"
        }
      }
    }

Or add via CLI:
    claude mcp add memoryos -- python /path/to/memos/mcp_server.py
"""

import json
import os
import sys

# Ensure project root is importable regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memoryos")


@mcp.tool()
def memory_add(content: str, source_type: str = "text", session_id: str = None) -> str:
    """
    Store content in MemoryOS memory.
    Extracts structured facts and stores them across SQLite, FAISS, and Kuzu.
    Returns facts_extracted, facts_added, and memory_ids.
    source_type: text | code | json | csv | pdf
    """
    import core.engine as engine
    result = engine.add(content=content, source_type=source_type, session_id=session_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_search(query: str, top_k: int = 5) -> str:
    """
    Search MemoryOS memory using hybrid retrieval (FAISS vector + BM25 keyword + Kuzu graph).
    Returns matching facts ranked by relevance and an assembled context string.
    """
    import core.engine as engine
    result = engine.search(query=query, top_k=top_k)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_augment(prompt: str, top_k: int = 3, force_inject: bool = False) -> str:
    """
    Augment a prompt with relevant memory context.
    Returns the original prompt with a [Memory Context] block prepended when relevant.
    Set force_inject=True to always inject context regardless of relevance check.
    """
    from core.augmenter import augment
    result = augment(prompt, top_k=top_k, force_inject=force_inject)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_delete(memory_id: str) -> str:
    """
    Delete a specific memory from all stores (SQLite, FAISS, Kuzu) by its memory_id.
    """
    import core.engine as engine
    result = engine.delete(memory_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def memory_graph(entity: str, hops: int = 2) -> str:
    """
    Get entity relationship subgraph from the Kuzu knowledge graph.
    Returns nodes and edges for the given entity up to `hops` traversal depth (max 4).
    """
    import core.engine as engine
    result = engine.get_graph(entity=entity, hops=hops)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
