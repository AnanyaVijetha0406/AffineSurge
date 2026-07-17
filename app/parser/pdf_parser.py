"""CT-200 PDF hierarchy reconstruction.

Uses PyMuPDF text extraction (these manuals are text PDFs, not scans).
OCR is not required for this corpus; we reconstruct hierarchy from
numbered headings and document order — critical because 3.4 appears
before 3.3 in the source.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import fitz


HEADING_RE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*)(?:\.\s*|\s+)(?P<title>[A-Z][^\n]{0,200})$"
)
# Also match titles that start lowercase after number (rare)
HEADING_RE_LOOSE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*)\.\s*(?P<title>.+)$"
)
PAGE_MARKER_RE = re.compile(r"^--\s*\d+\s+of\s+\d+\s*--$")
TABLE_ROW_SPLIT = re.compile(r"\s{2,}|\t")


@dataclass
class ParsedNode:
    heading: str
    section_number: str | None
    level: int
    body_text: str = ""
    node_type: str = "section"
    children: list["ParsedNode"] = field(default_factory=list)
    sort_order: int = 0

    def content_hash(self) -> str:
        payload = f"{self.section_number or ''}|{self.heading}|{self.body_text.strip()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def node_key(self) -> str:
        """Stable logical identity across versions.

        Prefer section number; for duplicate titles under different parents
        (e.g. two 'Error Codes'), include section number so they stay distinct.
        """
        if self.section_number:
            return f"sec:{self.section_number}"
        slug = re.sub(r"[^a-z0-9]+", "-", self.heading.lower()).strip("-")
        return f"title:{slug}"


def _level_from_section(section_number: str | None) -> int:
    if not section_number:
        return 1
    return section_number.count(".") + 1


def _is_page_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if PAGE_MARKER_RE.match(s):
        return True
    if s.startswith("CardioTrack CT-200") and "Manual" in s:
        return True
    return False


CLASSIFICATION_LIST_RE = re.compile(
    r"^\d+\.\s+(Normal|Elevated|Hypertension|Hypertensive)\b",
    re.IGNORECASE,
)


def _try_heading(line: str) -> tuple[str, str] | None:
    s = line.strip()
    # Classification bullets under 3.3 look like "1. Normal: ..." — not sections
    if CLASSIFICATION_LIST_RE.match(s):
        return None
    m = HEADING_RE.match(s)
    if m:
        return m.group("num"), m.group("title").strip()
    # Handle "2.1.1.1 Battery Life..." without requiring capital after space
    m2 = re.match(r"^(?P<num>\d+(?:\.\d+)+)\s+(?P<title>.+)$", s)
    if m2:
        title = m2.group("title").strip()
        # Avoid matching table values like "40–199 bpm"
        if re.match(r"^[A-Za-z]", title):
            return m2.group("num"), title
    m3 = re.match(r"^(?P<num>\d+)\.\s+(?P<title>[A-Z].+)$", s)
    if m3:
        return m3.group("num"), m3.group("title").strip()
    return None


def _extract_lines(pdf_path: str) -> list[str]:
    doc = fitz.open(pdf_path)
    lines: list[str] = []
    try:
        for page in doc:
            text = page.get_text("text")
            for raw in text.splitlines():
                line = raw.replace("\u00ad", "").strip()
                if _is_page_noise(line):
                    continue
                lines.append(line)
    finally:
        doc.close()
    return lines


def _looks_like_table_header(line: str) -> bool:
    lower = line.lower()
    return lower in {"parameter value", "code meaning device behavior"} or (
        "parameter" in lower and "value" in lower
    ) or (lower.startswith("code") and "meaning" in lower)


def parse_pdf(pdf_path: str) -> list[ParsedNode]:
    """Parse CT-200 manual into a forest of section nodes (document order)."""
    lines = _extract_lines(pdf_path)

    # Root document title
    roots: list[ParsedNode] = []
    stack: list[ParsedNode] = []
    sort_counter = 0

    def push_node(section_number: str | None, heading: str, node_type: str = "section") -> ParsedNode:
        nonlocal sort_counter
        level = _level_from_section(section_number)
        node = ParsedNode(
            heading=heading,
            section_number=section_number,
            level=level,
            node_type=node_type,
            sort_order=sort_counter,
        )
        sort_counter += 1

        while stack and stack[-1].level >= level:
            stack.pop()

        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
        return node

    # Skip document title lines at start
    i = 0
    while i < len(lines) and not _try_heading(lines[i]):
        i += 1

    current: ParsedNode | None = None
    body_buf: list[str] = []
    in_table = False
    table_buf: list[str] = []

    def flush_body() -> None:
        nonlocal body_buf, current
        if current is not None and body_buf:
            text = "\n".join(body_buf).strip()
            if text:
                current.body_text = (current.body_text + "\n" + text).strip() if current.body_text else text
            body_buf = []

    def flush_table() -> None:
        nonlocal in_table, table_buf, current, sort_counter
        if not table_buf or current is None:
            in_table = False
            table_buf = []
            return
        flush_body()
        table_text = "\n".join(table_buf).strip()
        table_node = ParsedNode(
            heading=f"Table under {current.section_number or current.heading}",
            section_number=None,
            level=current.level + 1,
            body_text=table_text,
            node_type="table",
            sort_order=sort_counter,
        )
        sort_counter += 1
        # Attach with unique key via parent path — node_key uses title slug
        table_node.heading = f"Table: {current.heading}"
        current.children.append(table_node)
        in_table = False
        table_buf = []

    while i < len(lines):
        line = lines[i]
        heading = _try_heading(line)

        if heading:
            if in_table:
                flush_table()
            flush_body()
            num, title = heading
            current = push_node(num, title)
            i += 1
            continue

        # Numbered classification list under a section (not a heading like 3.3)
        list_match = re.match(r"^(\d+)\.\s+(Normal|Elevated|Hypertension|Hypertensive).+", line)
        if list_match and current is not None:
            flush_body()
            # Collect consecutive numbered list items as a list node
            list_lines = [line]
            j = i + 1
            while j < len(lines):
                if re.match(r"^\d+\.\s+\S", lines[j]) and not _try_heading(lines[j]):
                    list_lines.append(lines[j])
                    j += 1
                else:
                    break
            list_node = ParsedNode(
                heading="Classification list",
                section_number=None,
                level=current.level + 1,
                body_text="\n".join(list_lines),
                node_type="list",
                sort_order=sort_counter,
            )
            sort_counter += 1
            current.children.append(list_node)
            i = j
            continue

        if _looks_like_table_header(line) or (
            in_table is False
            and current is not None
            and current.section_number in {"2.1", "4.2"}
            and re.match(r"^(Parameter|Code|Measurement|E\d)\b", line)
        ):
            if _looks_like_table_header(line) or line.lower().startswith("parameter") or line.lower().startswith("code"):
                if in_table:
                    flush_table()
                flush_body()
                in_table = True
                table_buf = [line]
                i += 1
                continue

        if in_table:
            # End table when next heading appears (handled above) or blank section break
            if _try_heading(line):
                flush_table()
                continue
            # Heuristic: lines that look like error codes / params stay in table
            if re.match(r"^E\d\b", line) or re.match(r"^[A-Z][a-z].+\s+\S+", line) or len(line.split()) <= 8:
                table_buf.append(line)
                i += 1
                continue
            flush_table()
            # fall through to body

        if current is not None:
            body_buf.append(line)
        i += 1

    if in_table:
        flush_table()
    flush_body()
    return roots


def flatten_nodes(roots: list[ParsedNode]) -> list[ParsedNode]:
    """Depth-first flatten preserving document order."""
    out: list[ParsedNode] = []

    def walk(n: ParsedNode) -> None:
        out.append(n)
        for c in n.children:
            walk(c)

    for r in roots:
        walk(r)
    return out
