"""
core/pdf_parser.py – PDF text extraction and smart chunking
Extracts text per page via pypdf2, detects document structure via LLM,
smart-chunks by section, and tags chunks HIGH/MED/LOW priority.
"""

import base64
import io
import re
from typing import List, Tuple, Dict


PRIORITY_HIGH = "HIGH"
PRIORITY_MED = "MED"
PRIORITY_LOW = "LOW"


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> List[Tuple[int, str]]:
    """
    Extract text from PDF bytes. Returns list of (page_num, text) tuples.
    Raises ValueError if no text extracted (likely scanned PDF).
    """
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append((i + 1, text.strip()))
        return pages
    except Exception as e:
        raise ValueError(f"PDF_PARSE_ERROR: {str(e)}")


def _detect_structure(full_text: str) -> str:
    """
    Use LLM to detect document type: 'paper', 'report', 'book', or 'unknown'.
    Falls back to 'unknown' if LLM call fails.
    """
    try:
        from core import llm
        prompt = (
            "Classify this document into exactly one type: paper, report, book, or unknown.\n"
            "Reply with ONLY the single word type, nothing else.\n\n"
            f"Document excerpt (first 500 chars):\n{full_text[:500]}"
        )
        result = llm.call(prompt).strip().lower()
        if result in {"paper", "report", "book"}:
            return result
        return "unknown"
    except Exception:
        return "unknown"


def _tag_section_priority(section_title: str, doc_type: str) -> str:
    """Assign priority based on section name and document type."""
    title_lower = section_title.lower()

    # Always high priority
    high_keywords = ["abstract", "introduction", "summary", "conclusion", "overview"]
    if any(kw in title_lower for kw in high_keywords):
        return PRIORITY_HIGH

    # Always low priority
    low_keywords = ["references", "bibliography", "acknowledgment", "appendix", "index"]
    if any(kw in title_lower for kw in low_keywords):
        return PRIORITY_LOW

    return PRIORITY_MED


def _split_by_sections(pages: List[Tuple[int, str]]) -> List[Tuple[str, str, str]]:
    """
    Attempt to split document into sections by detecting headers.
    Returns list of (section_title, content, priority).
    """
    full_text = "\n\n".join(text for _, text in pages if text)

    # Detect section headers: lines that are short, possibly numbered, ALL CAPS or Title Case
    section_pattern = re.compile(
        r'^(?:\d+[\.\d]*\s+)?([A-Z][A-Za-z\s]{3,60})$',
        re.MULTILINE
    )

    headers = list(section_pattern.finditer(full_text))
    if len(headers) < 2:
        return []  # No clear structure

    sections = []
    for i, header in enumerate(headers):
        title = header.group(0).strip()
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(full_text)
        content = full_text[start:end].strip()
        if content:
            priority = _tag_section_priority(title, "")
            sections.append((title, content, priority))

    return sections


def _chunk_section(title: str, content: str, priority: str) -> List[Dict]:
    """Split a section's content into chunks, applying fixed-size fallback."""
    from core.chunker import chunk_with_overlap

    # For HIGH priority sections (abstract etc), keep as one chunk
    if priority == PRIORITY_HIGH and len(content) < 3000:
        return [{"title": title, "content": content, "priority": priority}]

    # Extract tables and figures as separate chunks
    chunks = []
    table_pattern = re.compile(r'(Table\s+\d+[:\.].*?)(?=\n\n|\Z)', re.DOTALL | re.IGNORECASE)
    figure_pattern = re.compile(r'(Fig(?:ure)?\s+\d+[:\.].*?)(?=\n\n|\Z)', re.DOTALL | re.IGNORECASE)

    for match in table_pattern.finditer(content):
        chunks.append({"title": f"[TABLE] {title}", "content": match.group(0).strip(), "priority": PRIORITY_MED})
    for match in figure_pattern.finditer(content):
        chunks.append({"title": f"[FIGURE] {title}", "content": match.group(0).strip(), "priority": PRIORITY_LOW})

    # Remove extracted tables/figures from main content
    main_content = table_pattern.sub("", content)
    main_content = figure_pattern.sub("", main_content).strip()

    if main_content:
        sub_chunks = chunk_with_overlap(main_content, chunk_size=800, overlap=150)
        for sc in sub_chunks:
            chunks.append({"title": title, "content": sc, "priority": priority})

    return chunks


def parse_pdf(content: str, metadata: dict) -> List[str]:
    """
    Main entry point. Content is base64-encoded PDF bytes or raw text.
    Returns list of priority-tagged text segments like:
      "[HIGH] Abstract: This paper presents..."
    Raises ValueError if scanned PDF (no text layer).
    """
    # Try to decode as base64
    try:
        pdf_bytes = base64.b64decode(content)
        pages = _extract_text_from_pdf_bytes(pdf_bytes)
    except Exception:
        # Treat as already-extracted plain text
        from core.chunker import chunk_with_overlap
        chunks = chunk_with_overlap(content, chunk_size=800, overlap=150)
        return [f"[MED] {c}" for c in chunks]

    all_text = " ".join(text for _, text in pages if text)
    if not all_text.strip():
        raise ValueError("PDF appears to be a scanned image. Text extraction not supported in v1.")

    # Try structured section splitting
    sections = _split_by_sections(pages)

    if sections:
        # Structured document
        result = []
        for title, section_content, priority in sections:
            section_chunks = _chunk_section(title, section_content, priority)
            for chunk in section_chunks:
                result.append(f"[{chunk['priority']}] {chunk['title']}: {chunk['content']}")
        return result
    else:
        # No clear structure – fixed-size chunking
        from core.chunker import chunk_with_overlap
        chunks = chunk_with_overlap(all_text, chunk_size=800, overlap=150)
        return [f"[MED] {c}" for c in chunks]
