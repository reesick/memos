"""
core/code_parser.py – Source code chunking
Python: AST-based function/class extraction.
Other languages: regex-based function detection.
Fallback: semantic chunker.
Comments are preserved – often the most semantically rich part.
"""

import ast
import re
from typing import List


def _detect_language(content: str) -> str:
    """Heuristically detect programming language."""
    content_lower = content.lower()
    if "def " in content and ("import " in content or "class " in content):
        return "python"
    if re.search(r'\bfunction\s+\w+\s*\(', content) or re.search(r'=>', content):
        return "javascript"
    if re.search(r'\bpublic\s+\w+\s+\w+\s*\(', content):
        return "java"
    if re.search(r'#include\s*<', content) or re.search(r'\bvoid\s+\w+\s*\(', content):
        return "c"
    return "unknown"


def _parse_python(content: str) -> List[str]:
    """
    Use Python AST to extract functions and classes as individual chunks.
    Preserves comments (docstrings).
    Falls back to regex on SyntaxError.
    """
    chunks = []
    lines = content.splitlines(keepends=True)

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _parse_regex(content)

    # Extract import block
    import_lines = [
        l.strip() for l in lines
        if l.strip().startswith("import ") or l.strip().startswith("from ")
    ]
    if import_lines:
        chunks.append("Imports: " + "; ".join(import_lines))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip methods (they'll be captured under class)
            if not _is_top_level(node, tree):
                continue
            chunk = _extract_node_source(node, lines)
            if chunk:
                chunks.append(f"Function `{node.name}`:\n{chunk}")

        elif isinstance(node, ast.ClassDef):
            # Class summary chunk
            class_chunk = _extract_node_source(node, lines)
            if class_chunk:
                chunks.append(f"Class `{node.name}`:\n{class_chunk[:400]}")
            # Each method as a separate chunk
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_chunk = _extract_node_source(item, lines)
                    if method_chunk:
                        chunks.append(f"Method `{node.name}.{item.name}`:\n{method_chunk}")

    if not chunks:
        # AST parsed but nothing useful found – fallback
        from core.chunker import chunk_text
        return chunk_text(content)

    return chunks


def _is_top_level(node: ast.AST, tree: ast.Module) -> bool:
    """Check if a node is a direct child of the module (not nested in a class)."""
    for child in ast.iter_child_nodes(tree):
        if child is node:
            return True
    return False


def _extract_node_source(node: ast.AST, lines: List[str]) -> str:
    """Extract source lines for an AST node."""
    try:
        start = node.lineno - 1
        end = node.end_lineno
        return "".join(lines[start:end]).strip()
    except Exception:
        return ""


def _parse_regex(content: str) -> List[str]:
    """
    Regex-based function detection for non-Python languages.
    Detects function blocks by brace counting.
    """
    chunks = []
    # Match function signatures
    func_pattern = re.compile(
        r'(?:(?:public|private|protected|static|async|export|function|def|void|int|string|bool)\s+)*'
        r'(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{',
        re.MULTILINE
    )

    lines = content.splitlines()
    total_len = len(lines)
    found_something = False

    for match in func_pattern.finditer(content):
        func_name = match.group(1)
        # Find the body by counting braces
        start_pos = match.start()
        open_braces = 0
        end_pos = start_pos
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == '{':
                open_braces += 1
            elif char == '}':
                open_braces -= 1
                if open_braces == 0:
                    end_pos = i + 1
                    break

        func_text = content[start_pos:end_pos].strip()
        if func_text and len(func_text) > 20:
            chunks.append(f"Function `{func_name}`:\n{func_text}")
            found_something = True

    if not found_something:
        # Pure fallback
        from core.chunker import chunk_with_overlap
        return chunk_with_overlap(content, chunk_size=800, overlap=150)

    return chunks


def parse_code(content: str, metadata: dict) -> List[str]:
    """
    Main entry point.
    Detects language, uses best parser, falls back gracefully.
    Returns list of code chunk strings.
    """
    if not content or not content.strip():
        return []

    lang = metadata.get("language", None) or _detect_language(content)

    if lang == "python":
        return _parse_python(content)
    else:
        # Try regex for other languages
        chunks = _parse_regex(content)
        if chunks:
            return chunks
        # Final fallback
        from core.chunker import chunk_with_overlap
        return chunk_with_overlap(content, chunk_size=800, overlap=150)
