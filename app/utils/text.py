"""
Text Processing Utilities
==========================
Provides text cleaning and chunking functions for the document
ingestion pipeline. Text is cleaned of excessive whitespace while
preserving newlines for proper chunking.
"""

import re
from typing import List


def clean_text(text: str) -> str:
    """
    Cleans raw text while PRESERVING newline structure.
    - Replaces runs of spaces/tabs (but not newlines) with a single space.
    - Collapses 3+ consecutive newlines into 2 (paragraph breaks).
    - Strips leading/trailing whitespace.
    """
    if not text:
        return ""

    # Replace horizontal whitespace (spaces, tabs) runs with single space
    # but PRESERVE newlines so chunk_text can split on them later
    text = re.sub(r'[^\S\n]+', ' ', text)

    # Collapse excessive blank lines (3+ newlines → 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def chunk_text(text: str, lines_per_chunk: int = 15, overlap_lines: int = 5) -> List[str]:
    """
    Splits text into overlapping chunks based on lines.

    Args:
        text: The text to chunk (should have newlines preserved by clean_text).
        lines_per_chunk: Number of lines per chunk.
        overlap_lines: Number of lines that overlap between consecutive chunks.

    Returns:
        A list of text chunks with overlapping content for context continuity.
    """
    if not text:
        return []

    lines = text.split('\n')
    chunks = []
    step_size = lines_per_chunk - overlap_lines  # stride between chunk starts

    for i in range(0, len(lines), step_size):
        # Take lines_per_chunk lines (NOT step_size) to get the full chunk
        chunk_lines = lines[i: i + lines_per_chunk]

        chunk = '\n'.join(chunk_lines)

        if chunk.strip():
            chunks.append(chunk)

        # Stop if this chunk reached the end of the text
        if i + lines_per_chunk >= len(lines):
            break

    return chunks