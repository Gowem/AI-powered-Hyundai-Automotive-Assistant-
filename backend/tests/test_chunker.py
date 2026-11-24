import os
import tempfile

from app.ingestion.chunker import MAX_TABLE_TOKENS, chunk_pages, count_tokens, split_table, split_text
from app.ingestion.pdf_parser import PageContent, clean_pages, parse_pdf
from tests.fixtures.make_pdf import default_rows, make_brochure


def _parse(data: bytes) -> list[PageContent]:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, data)
    os.close(fd)
    try:
        return parse_pdf(path)
    finally:
        os.unlink(path)


def test_pdf_tables_become_markdown_and_pages_are_kept() -> None:
    data = make_brochure("Testmodel", default_rows("Testmodel"), ["A fictional paragraph about cabin comfort."])
    pages = clean_pages(_parse(data))
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[1].tables, "spec table should be detected on page 2"
    md = pages[1].tables[0]
    assert md.splitlines()[0].startswith("| Specification")
    assert md.splitlines()[1].startswith("| ---")
    assert "111 test-units" in md
    # table text is not duplicated in body text
    assert "111 test-units" not in pages[1].text

    chunks = chunk_pages(pages, "Alcazar", "Alcazar Test Brochure")
    assert {c.page_number for c in chunks} == {1, 2}
    table_chunks = [c for c in chunks if c.content_type == "table"]
    assert table_chunks and all(c.page_number == 2 for c in table_chunks)
    for c in chunks:
        assert c.content.startswith(f"[Vehicle: Alcazar | Document: Alcazar Test Brochure | Page {c.page_number} | ")
    assert "Prestige" in table_chunks[0].variants and "Signature" in table_chunks[0].variants


def test_large_table_split_by_rows_with_repeated_header() -> None:
    header = "| Feature | E | S | SX |"
    sep = "| --- | --- | --- | --- |"
    rows = [f"| Fictional feature number {i} with a long description | yes | no | yes |" for i in range(400)]
    md = "\n".join([header, sep, *rows])
    parts = split_table(md)
    assert len(parts) > 1
    seen_rows: list[str] = []
    for part in parts:
        lines = part.splitlines()
        assert lines[0] == header and lines[1] == sep
        assert count_tokens(part) <= MAX_TABLE_TOKENS
        for ln in lines[2:]:
            assert ln.startswith("| Fictional") and ln.endswith("|"), "row was split mid-row"
            seen_rows.append(ln)
    assert seen_rows == rows


def test_text_chunks_never_cross_pages_and_overlap() -> None:
    long_para = " ".join(f"Sentence {i} describes a fictional feature." for i in range(400))
    pages = [PageContent(1, long_para), PageContent(2, "Short page two text about safety airbags.")]
    chunks = chunk_pages(pages, "Creta", "Creta Doc")
    p1 = [c for c in chunks if c.page_number == 1]
    assert len(p1) > 1
    assert all("page two" not in c.content for c in p1)
    assert any(c.page_number == 2 for c in chunks)
    pieces = split_text(long_para)
    assert all(count_tokens(p) <= 600 for p in pieces)
    # overlap: the start of chunk 2 appears at the end of chunk 1
    assert pieces[1].split()[0:3] != pieces[0].split()[0:3]
    assert pieces[1][:40] in pieces[0]


def test_repeated_headers_removed_but_disclaimers_kept() -> None:
    pages = [
        PageContent(i, f"BRAND HEADER\nFuel efficiency as per ARAI certified test\nUnique content {i}\n{i}")
        for i in range(1, 6)
    ]
    cleaned = clean_pages(pages)
    for p in cleaned:
        assert "BRAND HEADER" not in p.text
        assert "ARAI" in p.text
        assert f"Unique content {p.page_number}" in p.text
        assert not p.text.strip().endswith(f"\n{p.page_number}")
