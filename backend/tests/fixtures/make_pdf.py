"""Generate tiny synthetic brochure PDFs for tests. Contents are fictional placeholders."""

import pymupdf


def draw_table(
    page: pymupdf.Page, x: float, y: float, rows: list[list[str]], col_w: float = 160, row_h: float = 22
) -> float:
    ncols = len(rows[0])
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x + c * col_w, y + r * row_h, x + (c + 1) * col_w, y + (r + 1) * row_h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_textbox(rect + (4, 4, -4, -2), cell, fontsize=9)
    return y + len(rows) * row_h + ncols * 0


def make_brochure(vehicle: str, spec_rows: list[list[str]], paragraphs: list[str], extra_pages: int = 0) -> bytes:
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), f"Hyundai {vehicle}", fontsize=24)
    y = 110
    for para in paragraphs:
        p1.insert_textbox(pymupdf.Rect(72, y, 520, y + 120), para, fontsize=11)
        y += 130
    p2 = doc.new_page()
    p2.insert_text((72, 60), "Specifications", fontsize=18)
    draw_table(p2, 72, 80, spec_rows)
    for i in range(extra_pages):
        p = doc.new_page()
        p.insert_textbox(pymupdf.Rect(72, 72, 520, 700), f"{vehicle} safety page {i}. " * 20, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def default_rows(vehicle: str) -> list[list[str]]:
    return [
        ["Specification", f"{vehicle} Prestige", f"{vehicle} Signature"],
        ["Engine", "ZX-100 test engine", "ZX-200 test engine"],
        ["Max Power", "111 test-units", "222 test-units"],
        ["Airbags", "4 test airbags", "8 test airbags"],
    ]
