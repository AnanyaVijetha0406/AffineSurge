from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DocumentVersion, Node, Selection, SelectionItem
from app.schemas import SelectionCreate, SelectionResponse

router = APIRouter(prefix="/selections", tags=["selections"])


@router.post("", response_model=SelectionResponse)
def create_selection(req: SelectionCreate, db: Session = Depends(get_db)):
    if not req.node_ids:
        raise HTTPException(status_code=400, detail="node_ids required")

    existing = db.query(Selection).filter(Selection.name == req.name).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Selection name already exists")

    nodes = db.query(Node).filter(Node.id.in_(req.node_ids)).all()
    if len(nodes) != len(set(req.node_ids)):
        raise HTTPException(status_code=404, detail="One or more node_ids not found")

    version_ids = {n.version_id for n in nodes}
    if len(version_ids) != 1:
        raise HTTPException(status_code=400, detail="All nodes must belong to the same document version")

    version_id = req.version_id or nodes[0].version_id
    if version_id != nodes[0].version_id:
        raise HTTPException(status_code=400, detail="version_id does not match node versions")

    ver = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).one()

    selection = Selection(
        name=req.name,
        document_id=ver.document_id,
        version_id=version_id,
    )
    db.add(selection)
    db.flush()

    for n in nodes:
        db.add(
            SelectionItem(
                selection_id=selection.id,
                node_id=n.id,
                node_key=n.node_key,
                heading_snapshot=n.heading,
                body_snapshot=n.body_text,
                content_hash_snapshot=n.content_hash,
                version_number=ver.version_number,
            )
        )
    db.commit()
    db.refresh(selection)

    return SelectionResponse(
        id=selection.id,
        name=selection.name,
        version_id=selection.version_id,
        version_number=ver.version_number,
        node_ids=[n.id for n in nodes],
        created_at=selection.created_at,
    )


@router.get("/{selection_id}", response_model=SelectionResponse)
def get_selection(selection_id: int, db: Session = Depends(get_db)):
    selection = db.query(Selection).filter(Selection.id == selection_id).one_or_none()
    if not selection:
        raise HTTPException(status_code=404, detail="Selection not found")
    ver = db.query(DocumentVersion).filter(DocumentVersion.id == selection.version_id).one()
    items = db.query(SelectionItem).filter(SelectionItem.selection_id == selection.id).all()
    return SelectionResponse(
        id=selection.id,
        name=selection.name,
        version_id=selection.version_id,
        version_number=ver.version_number,
        node_ids=[i.node_id for i in items],
        created_at=selection.created_at,
    )
