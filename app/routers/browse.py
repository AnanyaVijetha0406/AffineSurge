from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Document, DocumentVersion, Node
from app.schemas import NodeChangeInfo, NodeDetail, NodeSummary
from app.services.ingestion import lightweight_diff

router = APIRouter(prefix="/browse", tags=["browse"])


def _resolve_version(db: Session, version: int | None) -> DocumentVersion:
    settings = get_settings()
    doc = db.query(Document).filter(Document.slug == settings.document_slug).one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not ingested yet")
    q = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id)
    if version is None:
        ver = q.order_by(DocumentVersion.version_number.desc()).first()
    else:
        ver = q.filter(DocumentVersion.version_number == version).one_or_none()
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return ver


def _to_summary(n: Node, child_count: int = 0) -> NodeSummary:
    return NodeSummary(
        id=n.id,
        node_key=n.node_key,
        heading=n.heading,
        section_number=n.section_number,
        level=n.level,
        content_hash=n.content_hash,
        node_type=n.node_type,
        changed_from_previous=n.changed_from_previous,
        child_count=child_count,
    )


@router.get("/sections", response_model=list[NodeSummary])
def list_top_sections(version: int | None = None, db: Session = Depends(get_db)):
    ver = _resolve_version(db, version)
    nodes = (
        db.query(Node)
        .filter(Node.version_id == ver.id, Node.parent_id.is_(None))
        .order_by(Node.sort_order)
        .all()
    )
    result = []
    for n in nodes:
        cc = db.query(Node).filter(Node.parent_id == n.id).count()
        result.append(_to_summary(n, cc))
    return result


@router.get("/nodes/{node_id}", response_model=NodeDetail)
def get_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    ver = db.query(DocumentVersion).filter(DocumentVersion.id == node.version_id).one()
    children = db.query(Node).filter(Node.parent_id == node.id).order_by(Node.sort_order).all()
    return NodeDetail(
        id=node.id,
        node_key=node.node_key,
        heading=node.heading,
        section_number=node.section_number,
        level=node.level,
        body_text=node.body_text,
        content_hash=node.content_hash,
        node_type=node.node_type,
        parent_id=node.parent_id,
        version_id=node.version_id,
        version_number=ver.version_number,
        changed_from_previous=node.changed_from_previous,
        children=[_to_summary(c) for c in children],
    )


@router.get("/search", response_model=list[NodeSummary])
def search_nodes(
    q: str = Query(..., min_length=1),
    version: int | None = None,
    db: Session = Depends(get_db),
):
    ver = _resolve_version(db, version)
    like = f"%{q}%"
    nodes = (
        db.query(Node)
        .filter(
            Node.version_id == ver.id,
            (Node.heading.ilike(like)) | (Node.body_text.ilike(like)),
        )
        .order_by(Node.sort_order)
        .limit(50)
        .all()
    )
    return [_to_summary(n) for n in nodes]


@router.get("/nodes/{node_id}/changes", response_model=NodeChangeInfo)
def node_changes(
    node_id: int,
    compare_to_version: int | None = None,
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    ver = db.query(DocumentVersion).filter(DocumentVersion.id == node.version_id).one()
    doc = db.query(Document).filter(Document.id == ver.document_id).one()

    if compare_to_version is None:
        # Compare against previous version if any
        other = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == ver.version_number - 1,
            )
            .one_or_none()
        )
        if other is None:
            return NodeChangeInfo(
                node_id=node.id,
                node_key=node.node_key,
                heading=node.heading,
                changed=False,
                change_type="unchanged",
                from_version=None,
                to_version=ver.version_number,
                current_hash=node.content_hash,
                diff_summary="No prior version to compare.",
            )
    else:
        other = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version_number == compare_to_version,
            )
            .one_or_none()
        )
        if other is None:
            raise HTTPException(status_code=404, detail="compare_to_version not found")

    other_node = (
        db.query(Node)
        .filter(Node.version_id == other.id, Node.node_key == node.node_key)
        .one_or_none()
    )
    if other_node is None:
        return NodeChangeInfo(
            node_id=node.id,
            node_key=node.node_key,
            heading=node.heading,
            changed=True,
            change_type="new",
            from_version=other.version_number,
            to_version=ver.version_number,
            current_hash=node.content_hash,
            diff_summary="No matching node_key in compared version.",
        )

    if other_node.content_hash == node.content_hash:
        return NodeChangeInfo(
            node_id=node.id,
            node_key=node.node_key,
            heading=node.heading,
            changed=False,
            change_type="unchanged",
            from_version=other.version_number,
            to_version=ver.version_number,
            previous_hash=other_node.content_hash,
            current_hash=node.content_hash,
            diff_summary="Content hash identical.",
        )

    return NodeChangeInfo(
        node_id=node.id,
        node_key=node.node_key,
        heading=node.heading,
        changed=True,
        change_type="modified",
        from_version=other.version_number,
        to_version=ver.version_number,
        previous_hash=other_node.content_hash,
        current_hash=node.content_hash,
        diff_summary=lightweight_diff(other_node.body_text, node.body_text),
    )
