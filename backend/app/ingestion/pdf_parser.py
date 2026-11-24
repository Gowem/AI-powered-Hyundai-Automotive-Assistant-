"""PDF parsing with PyMuPDF: body text + spec tables (as Markdown) per page."""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger("app.ingestion")

MIN_TEXT_CHARS = 40


@dataclass
class PageContent:
    page_number: int  # 1-based
    text: str
    tables: list[str] = field(default_factory=list)
    needs_ocr: bool = False
    ocr_text: str | None = None


def _clean_cell(cell: object) -> str:
    if cell is None:
        return ""
    s = str(cell).replace("\n", " ").replace("|", "/")
    return re.sub(r"\s+", " ", s).strip()


def table_to_markdown(rows: list[list[object]], header: list[object] | None = None) -> str | None:
    cleaned = [[_clean_cell(c) for c in row] for row in rows]
    if header and any(h for h in header):
        head = [_clean_cell(h) for h in header]
        if cleaned and cleaned[0] == head:
            cleaned = cleaned[1:]
        cleaned = [head, *cleaned]
    cleaned = [r for r in cleaned if any(c for c in r)]
    if len(cleaned) < 2:
        return None
    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]
    keep = [i for i in range(width) if any(r[i] for r in cleaned)]
    if len(keep) < 2:
        return None
    cleaned = [[r[i] for i in keep] for r in cleaned]
    head, *body = cleaned
    head = [h or f"Column {i + 1}" for i, h in enumerate(head)]
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _normalise_text(text: str) -> str:
    text = text.replace(" ", " ").replace("•", "-").replace("", "-")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _rect_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return inter.get_area() / max(a.get_area(), 1e-6)


def _extract_rows(page: pymupdf.Page, tab: object, words: list[tuple]) -> list[list[object]]:
    """Assign page words to cell bboxes (one text extraction per page; keeps word spacing)."""
    rows: list[list[object]] = []
    for row in getattr(tab, "rows", []):
        cells: list[object] = []
        for bbox in row.cells:
            if not bbox:
                cells.append(None)
                continue
            x0, y0, x1, y1 = bbox
            inside = [w for w in words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
            inside.sort(key=lambda w: (w[5], w[6], w[7]))  # block, line, word order
            cells.append(" ".join(w[4] for w in inside))
        rows.append(cells)
    if not rows:
        rows = tab.extract()  # type: ignore[attr-defined]
    return rows


def parse_page(page: pymupdf.Page) -> PageContent:
    tables_md: list[str] = []
    table_rects: list[pymupdf.Rect] = []
    try:
        found = page.find_tables()
        words = page.get_text("words") if found.tables else []
        for tab in found.tables:
            try:
                md = table_to_markdown(_extract_rows(page, tab, words))
            except Exception:  # noqa: BLE001 - a broken table must not break the page
                logger.debug("table extraction failed on page %s", page.number + 1, exc_info=True)
                continue
            if md:
                tables_md.append(md)
                table_rects.append(pymupdf.Rect(tab.bbox))
    except Exception:  # noqa: BLE001
        logger.debug("find_tables failed on page %s", page.number + 1, exc_info=True)

    blocks = page.get_text("blocks", sort=True)
    parts: list[str] = []
    for b in blocks:
        if b[6] != 0:  # image block
            continue
        rect = pymupdf.Rect(b[:4])
        if any(_rect_overlap(rect, tr) > 0.6 for tr in table_rects):
            continue  # already captured inside a Markdown table
        parts.append(b[4])
    text = _normalise_text("\n".join(parts))
    total_chars = len(text) + sum(len(t) for t in tables_md)
    return PageContent(page_number=page.number + 1, text=text, tables=tables_md, needs_ocr=total_chars < MIN_TEXT_CHARS)


def parse_pdf(path: str) -> list[PageContent]:
    pages: list[PageContent] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pages.append(parse_page(page))
    return pages


def render_page_png(path: str, page_number: int, dpi: int = 150) -> bytes:
    with pymupdf.open(path) as doc:
        pix = doc[page_number - 1].get_pixmap(dpi=dpi)
        return pix.tobytes("png")


def page_count(path: str) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


_PAGE_NUM = re.compile(r"^(page\s*)?\d{1,3}(\s*/\s*\d{1,3})?$", re.IGNORECASE)
_LEGAL_NOISE = re.compile(
    r"^(all rights reserved\.?|copyright.*|©.*hyundai.*|www\.hyundai\.(com|co\.in)\S*|scan (the )?qr code.*)$",
    re.IGNORECASE,
)
# Disclaimers that qualify specs must be kept.
_KEEP = re.compile(r"arai|certified|test condition|as per|homologat|km/l|kmpl|variant", re.IGNORECASE)


def clean_pages(pages: list[PageContent]) -> list[PageContent]:
    """Remove repeated headers/footers (>50% of pages), page numbers and pure legal boilerplate."""
    if len(pages) >= 4:
        counts: Counter[str] = Counter()
        for p in pages:
            counts.update({ln.strip().lower() for ln in p.text.splitlines() if ln.strip()})
        threshold = len(pages) * 0.5
        repeated = {ln for ln, c in counts.items() if c > threshold and not _KEEP.search(ln)}
    else:
        repeated = set()
    for p in pages:
        kept: list[str] = []
        for ln in p.text.splitlines():
            s = ln.strip()
            if s and (s.lower() in repeated or _PAGE_NUM.match(s) or (_LEGAL_NOISE.match(s) and not _KEEP.search(s))):
                continue
            kept.append(ln)
        p.text = _normalise_text("\n".join(kept))
    return pages
