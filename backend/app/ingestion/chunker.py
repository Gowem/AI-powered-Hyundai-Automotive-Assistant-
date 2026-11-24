"""Page- and table-aware chunking.

Rules: ~500-token text chunks with 80-token overlap, never across pages; each table is its
own chunk and is split by rows (header repeated) only above 900 tokens. Every chunk starts
with a context header that is also embedded.
"""

import math
import re
from dataclasses import dataclass, field

from app.ingestion.metadata import detect_section, detect_variants
from app.ingestion.pdf_parser import PageContent

TARGET_TOKENS = 500
OVERLAP_TOKENS = 80
MAX_TABLE_TOKENS = 900


def count_tokens(text: str) -> int:
    """Cheap approximation (~4 chars/token for English, never below word count)."""
    return max(len(text.split()), math.ceil(len(text) / 4))


@dataclass
class ChunkData:
    page_number: int
    chunk_index: int
    section: str
    variants: list[str]
    content_type: str
    content: str
    token_count: int
    body: str = field(repr=False, default="")


def context_header(vehicle: str, document_name: str, page: int, section: str) -> str:
    return f"[Vehicle: {vehicle} | Document: {document_name} | Page {page} | Section: {section}]"


def split_table(md: str, max_tokens: int = MAX_TABLE_TOKENS) -> list[str]:
    lines = md.strip().splitlines()
    if count_tokens(md) <= max_tokens or len(lines) <= 3:
        return [md.strip()]
    header, sep, rows = lines[0], lines[1], lines[2:]
    parts: list[str] = []
    current: list[str] = []
    for row in rows:
        if current and count_tokens("\n".join([header, sep, *current, row])) > max_tokens:
            parts.append("\n".join([header, sep, *current]))
            current = []
        current.append(row)
    if current:
        parts.append("\n".join([header, sep, *current]))
    return parts


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _units(text: str) -> list[str]:
    """Split text into paragraph/sentence units small enough to pack."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if count_tokens(para) <= TARGET_TOKENS:
            units.append(para)
            continue
        for sent in _SENT_SPLIT.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if count_tokens(sent) <= TARGET_TOKENS:
                units.append(sent)
            else:  # pathological run-on text: hard split on words
                words = sent.split()
                step = int(TARGET_TOKENS * 0.75)
                units.extend(" ".join(words[i : i + step]) for i in range(0, len(words), step))
    return units


def split_text(text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    units = _units(text)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for u in units:
        t = count_tokens(u)
        if current and size + t > target:
            chunks.append("\n\n".join(current))
            # carry overlap from the tail of the previous chunk
            carry: list[str] = []
            carry_size = 0
            for prev in reversed(current):
                pt = count_tokens(prev)
                if carry_size + pt > overlap:
                    break
                carry.insert(0, prev)
                carry_size += pt
            if not carry and current:
                tail_words = current[-1].split()[-overlap:]
                carry = [" ".join(tail_words)]
                carry_size = count_tokens(carry[0])
            current, size = carry, carry_size
        current.append(u)
        size += t
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_pages(pages: list[PageContent], vehicle: str, document_name: str) -> list[ChunkData]:
    out: list[ChunkData] = []
    idx = 0
    for page in pages:
        page_text = page.ocr_text if page.ocr_text else page.text
        page_section = detect_section(page_text + "\n" + "\n".join(page.tables))
        is_ocr = bool(page.ocr_text)

        for table in page.tables:
            section = detect_section(table, fallback=page_section, is_table=True)
            variants = detect_variants(table, is_table=True)
            for part in split_table(table):
                content = context_header(vehicle, document_name, page.page_number, section) + "\n" + part
                out.append(
                    ChunkData(page.page_number, idx, section, variants, "table", content, count_tokens(content), part)
                )
                idx += 1

        if page_text.strip():
            for piece in split_text(page_text):
                if len(piece.strip()) < 20:
                    continue
                has_table = is_ocr and "|---" in piece.replace(" ", "")
                section = detect_section(piece, fallback=page_section, is_table=has_table)
                variants = detect_variants(piece, is_table=has_table)
                content = context_header(vehicle, document_name, page.page_number, section) + "\n" + piece
                out.append(
                    ChunkData(
                        page.page_number,
                        idx,
                        section,
                        variants,
                        "ocr" if is_ocr else "text",
                        content,
                        count_tokens(content),
                        piece,
                    )
                )
                idx += 1
    return out
