"""Unit tests targeting CT-200 structural irregularities."""

from pathlib import Path

from app.parser.pdf_parser import flatten_nodes, parse_pdf

DATA = Path(__file__).resolve().parents[1] / "data"
V1 = DATA / "ct200_manual.pdf"
V2 = DATA / "ct200_manual_v2.pdf"


def _by_section(roots):
    return {n.section_number: n for n in flatten_nodes(roots) if n.section_number}


def test_out_of_order_headings_preserve_document_order():
    """3.4 Auto Shutoff appears before 3.3 in the PDF — order must follow doc, not number sort."""
    roots = parse_pdf(str(V1))
    flat = [n for n in flatten_nodes(roots) if n.section_number in {"3.3", "3.4"}]
    assert [n.section_number for n in flat] == ["3.4", "3.3"]
    assert flat[0].sort_order < flat[1].sort_order


def test_deep_heading_2_1_1_1_and_parent_chain():
    """2.1.1.1 exists without an intermediate 2.1.1 heading — still nests under 2.1."""
    roots = parse_pdf(str(V1))
    by_sec = _by_section(roots)
    assert "2.1.1.1" in by_sec
    deep = by_sec["2.1.1.1"]
    assert deep.level == 4
    # Parent should be 2.1 (level 2), skipping missing 2.1.1
    parent = None
    for n in flatten_nodes(roots):
        if deep in n.children:
            parent = n
            break
    assert parent is not None
    assert parent.section_number == "2.1"


def test_duplicate_error_codes_headings_distinct_keys():
    """4.2 Error Codes and 7.1 Error Codes must be distinct nodes with distinct keys."""
    roots = parse_pdf(str(V1))
    by_sec = _by_section(roots)
    assert "4.2" in by_sec and "7.1" in by_sec
    a, b = by_sec["4.2"], by_sec["7.1"]
    assert "Error Codes" in a.heading
    assert "Error Codes" in b.heading
    assert a.node_key() != b.node_key()
    assert a.node_key() == "sec:4.2"
    assert b.node_key() == "sec:7.1"
    # Different parents
    parents = {}
    for n in flatten_nodes(roots):
        for c in n.children:
            if c.section_number in {"4.2", "7.1"}:
                parents[c.section_number] = n.section_number
    assert parents["4.2"] == "4"
    assert parents["7.1"] == "7"


def test_v2_has_new_sections_and_changed_battery_text():
    v1 = _by_section(parse_pdf(str(V1)))
    v2 = _by_section(parse_pdf(str(V2)))
    assert "5.3" in v2
    assert "5.3" not in v1
    assert v1["2.1.1.1"].content_hash() != v2["2.1.1.1"].content_hash()
    assert "300" in v1["2.1.1.1"].body_text or "300" in v1["2.1.1.1"].heading
    # body should mention cycles
    assert "250" in v2["2.1.1.1"].body_text
