"""Context numbering and [n] citation parsing."""

import logging
import re

from app.rag.retriever import RetrievedChunk
from app.schemas import SourceOut

logger = logging.getLogger("app.rag")

_CITE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
_HEADER = re.compile(r"^\[Vehicle:[^\]]*\]\s*\n?")


def strip_header(content: str) -> str:
    return _HEADER.sub("", content, count=1).strip()


def format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for n, c in enumerate(chunks, start=1):
        label = f"{c.document_name}, page {c.page_number}, {c.section or 'Other'}"
        blocks.append(f"[{n}] ({label})\n{strip_header(c.content)}")
    return "\n\n".join(blocks)


def cited_numbers(text: str) -> list[int]:
    nums: list[int] = []
    for m in _CITE.finditer(text):
        for part in m.group(1).split(","):
            n = int(part.strip())
            if n not in nums:
                nums.append(n)
    return nums


def _source(n: int, c: RetrievedChunk) -> SourceOut:
    snippet = re.sub(r"\s+", " ", strip_header(c.content))[:200]
    return SourceOut(
        n=n,
        document_id=c.document_id,
        document_name=c.document_name,
        vehicle_model=c.vehicle_model,
        page=c.page_number,
        snippet=snippet,
    )


def build_sources(answer: str, chunks: list[RetrievedChunk]) -> list[SourceOut]:
    """Only the cited sources; top 3 as a fallback when the model cited nothing."""
    valid = [n for n in cited_numbers(answer) if 1 <= n <= len(chunks)]
    if not valid and chunks:
        logger.warning("answer contained no valid citations; attaching top sources")
        return [_source(n, chunks[n - 1]) for n in range(1, min(3, len(chunks)) + 1)]
    return [_source(n, chunks[n - 1]) for n in sorted(valid)]


def strip_invalid_citations(answer: str, n_sources: int) -> str:
    """Remove citation markers that point outside the source list."""

    def repl(m: re.Match[str]) -> str:
        nums = [p.strip() for p in m.group(1).split(",") if 1 <= int(p.strip()) <= n_sources]
        return "".join(f"[{n}]" for n in nums)

    return _CITE.sub(repl, answer)
