"""PDF parsing with PyMuPDF: body text + spec tables (as Markdown) per page."""

import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger("app.ingestion")

MIN_TEXT_CHARS = 40
MIN_TABLE_DRAWINGS = 10  # ruled tables need lines; skip table detection on pages without them


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


def _word_gaps(words: list[tuple], x0: float, x1: float) -> list[tuple[float, float]]:
    """Empty vertical gutters (start, end) between x0 and x1 where no word overlaps."""
    spans = sorted((w[0], w[2]) for w in words if w[2] > x0 and w[0] < x1)
    gaps: list[tuple[float, float]] = []
    cursor = x0
    for a, b in spans:
        if a > cursor:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < x1:
        gaps.append((cursor, x1))
    return gaps


_PANEL_HEADERS = {"Variant", "Variants", "Items"}


def panels(page: pymupdf.Page, words: list[tuple]) -> list[pymupdf.Rect]:
    """Split pages that hold several side-by-side tables into one clip per table.

    Each spec/feature table starts with a header cell such as "Variant" or "Items"; a cut is made
    in the empty gutter just left of every such header that is not at the page's left edge.
    Very wide brochure spreads without such headers are split into equal panels.
    """
    r = page.rect
    gaps = [g for g in _word_gaps(words, r.x0, r.x1) if g[1] - g[0] >= 4]
    heads = sorted({round(w[0]) for w in words if w[4] in _PANEL_HEADERS and w[1] < r.y0 + r.height * 0.25})
    cuts: list[float] = []
    for x in heads:
        if x < r.x0 + r.width * 0.1 or (cuts and x - cuts[-1] < r.width * 0.08):
            continue
        before = [g for g in gaps if g[1] <= x + 1]
        cuts.append((before[-1][0] + before[-1][1]) / 2 if before else x - 2)
    if not cuts and r.width >= 1.8 * r.height:
        n = max(2, round(r.width / (r.height * 0.9)))
        for k in range(1, n):
            target = r.x0 + r.width * k / n
            near = [(g[0] + g[1]) / 2 for g in gaps if abs((g[0] + g[1]) / 2 - target) <= r.width * 0.06]
            cuts.append(min(near, key=lambda c: abs(c - target)) if near else target)
    xs = [r.x0, *sorted(cuts), r.x1]
    return [pymupdf.Rect(xs[i], r.y0, xs[i + 1], r.y1) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 20]


def layout_rows(words: list[tuple], clip: pymupdf.Rect, gap_factor: float = 1.2) -> list[str]:
    """Rebuild table rows from word positions: same baseline = same row, wide gap = new cell.

    Brochure spec sheets put row labels outside the ruled cells, so pure line-based table
    detection loses them; this keeps "Max. power | 84.4 kW (115 PS) | ..." together.
    """
    seen: set[tuple[str, int, int]] = set()
    ws = []
    for w in words:
        key = (w[4], round(w[0]), round(w[1]))  # brochures often overprint identical text
        if clip.x0 <= (w[0] + w[2]) / 2 < clip.x1 and key not in seen:
            seen.add(key)
            ws.append(w)
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[dict] = []
    for w in ws:
        yc, h = (w[1] + w[3]) / 2, w[3] - w[1]
        if lines and abs(lines[-1]["y"] - yc) <= max(2.0, 0.35 * h):
            lines[-1]["w"].append(w)
        else:
            lines.append({"y": yc, "w": [w]})
    out: list[str] = []
    for ln in lines:
        row = sorted(ln["w"], key=lambda w: w[0])
        h = statistics.median([w[3] - w[1] for w in row])
        cells: list[list[str]] = [[row[0][4]]]
        for prev, cur in zip(row, row[1:], strict=False):
            if cur[0] - prev[2] > gap_factor * h:
                cells.append([cur[4]])
            else:
                cells[-1].append(cur[4])
        out.append(" | ".join(" ".join(c) for c in cells).replace("\u00a0", " "))
    return out


def parse_page(page: pymupdf.Page) -> PageContent:
    """Body text for normal pages; row-aligned table text for pages with ruled spec tables."""
    is_table_page = False
    try:
        # use_layout=False: MuPDF's layout analysis costs ~400 MB per brochure page (OOM on 512 MB hosts).
        # Detection only decides whether this is a spec-table page; rows are rebuilt by layout_rows().
        if len(page.get_drawings()) >= MIN_TABLE_DRAWINGS:
            found = page.find_tables(use_layout=False)
            is_table_page = any(t.row_count >= 3 and t.col_count >= 2 for t in found.tables)
    except Exception:  # noqa: BLE001 - table detection is best effort
        logger.debug("find_tables failed on page %s", page.number + 1, exc_info=True)

    if is_table_page:
        words = page.get_text("words")
        tables = []
        for clip in panels(page, words):
            rows = [r for r in layout_rows(words, clip) if r.strip()]
            if rows:
                tables.append("\n".join(rows))
        chars = sum(len(t) for t in tables)
        return PageContent(page.number + 1, "", tables, needs_ocr=chars < MIN_TEXT_CHARS)

    blocks = page.get_text("blocks", sort=True)
    text = _normalise_text("\n".join(b[4] for b in blocks if b[6] == 0))
    return PageContent(page_number=page.number + 1, text=text, tables=[], needs_ocr=len(text) < MIN_TEXT_CHARS)


def parse_pdf(path: str) -> list[PageContent]:
    pages: list[PageContent] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pages.append(parse_page(page))
            pymupdf.TOOLS.store_shrink(100)  # release MuPDF's object cache between pages
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
