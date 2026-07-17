from __future__ import annotations

import difflib
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentVersion, Node
from app.parser.pdf_parser import ParsedNode, flatten_nodes, parse_pdf


def _get_or_create_document(db: Session, title: str) -> Document:
    settings = get_settings()
    doc = db.query(Document).filter(Document.slug == settings.document_slug).one_or_none()
    if doc is None:
        doc = Document(slug=settings.document_slug, title=title)
        db.add(doc)
        db.flush()
    return doc


def _persist_tree(
    db: Session,
    version: DocumentVersion,
    roots: list[ParsedNode],
    previous_by_key: dict[str, Node],
) -> tuple[int, int, int]:
    """Insert nodes; return (changed, new, unchanged) counts."""
    changed = new = unchanged = 0
    key_to_id: dict[str, int] = {}

    flat = flatten_nodes(roots)
    # First pass: create all nodes without parent_id, then wire parents
    created: list[tuple[ParsedNode, Node, str | None]] = []

    parent_key_stack: list[tuple[int, str]] = []  # (level, node_key)

    for pn in flat:
        # Determine parent key from stack of ancestors by level
        while parent_key_stack and parent_key_stack[-1][0] >= pn.level:
            parent_key_stack.pop()
        parent_key = parent_key_stack[-1][1] if parent_key_stack else None

        # Unique node_key for tables/lists under same parent
        base_key = pn.node_key()
        if pn.node_type in {"table", "list"}:
            parent_ref = parent_key or "root"
            base_key = f"{parent_ref}/{pn.node_type}:{pn.sort_order}"

        ch = pn.content_hash()
        prev = previous_by_key.get(base_key)
        if prev is None:
            new += 1
            changed_flag = True
            prev_id = None
        elif prev.content_hash != ch:
            changed += 1
            changed_flag = True
            prev_id = prev.id
        else:
            unchanged += 1
            changed_flag = False
            prev_id = prev.id

        node = Node(
            version_id=version.id,
            node_key=base_key,
            heading=pn.heading,
            section_number=pn.section_number,
            level=pn.level,
            body_text=pn.body_text,
            content_hash=ch,
            parent_id=None,
            sort_order=pn.sort_order,
            node_type=pn.node_type,
            changed_from_previous=changed_flag if previous_by_key else False,
            previous_node_id=prev_id,
        )
        db.add(node)
        db.flush()
        key_to_id[base_key] = node.id
        created.append((pn, node, parent_key))
        parent_key_stack.append((pn.level, base_key))

    for pn, node, parent_key in created:
        if parent_key and parent_key in key_to_id:
            node.parent_id = key_to_id[parent_key]

    db.flush()
    return changed, new, unchanged


def ingest_pdf(db: Session, pdf_path: str, version_number: int | None = None) -> dict:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    roots = parse_pdf(str(path))
    doc = _get_or_create_document(db, title="CardioTrack CT-200 Technical & User Manual")

    if version_number is None:
        latest = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        version_number = 1 if latest is None else latest.version_number + 1

    existing = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == version_number,
        )
        .one_or_none()
    )
    if existing is not None:
        raise ValueError(f"Version {version_number} already exists for this document")

    previous_by_key: dict[str, Node] = {}
    if version_number > 1:
        prev_ver = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == version_number - 1,
            )
            .one_or_none()
        )
        if prev_ver:
            for n in db.query(Node).filter(Node.version_id == prev_ver.id).all():
                previous_by_key[n.node_key] = n

    version = DocumentVersion(
        document_id=doc.id,
        version_number=version_number,
        source_filename=path.name,
    )
    db.add(version)
    db.flush()

    changed, new, unchanged = _persist_tree(db, version, roots, previous_by_key)
    db.commit()

    node_count = db.query(Node).filter(Node.version_id == version.id).count()
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "node_count": node_count,
        "changed_nodes": changed,
        "new_nodes": new,
        "unchanged_nodes": unchanged,
    }


def lightweight_diff(old_text: str, new_text: str, max_lines: int = 8) -> str:
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    diff = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=1)
    )
    if not diff:
        return "No textual diff (hash differed only on heading/whitespace normalization)."
    clipped = diff[: max_lines + 2]
    if len(diff) > len(clipped):
        clipped.append(f"... ({len(diff) - len(clipped)} more diff lines)")
    return "\n".join(clipped)
