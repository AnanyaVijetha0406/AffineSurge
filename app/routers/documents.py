from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import IngestRequest, IngestResponse
from app.services.ingestion import ingest_pdf

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    path = Path(req.pdf_path)
    if not path.is_absolute():
        # Resolve relative to project root
        path = Path.cwd() / path
    try:
        result = ingest_pdf(db, str(path), req.version_number)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return result


@router.get("/versions")
def list_versions(db: Session = Depends(get_db)):
    from app.config import get_settings
    from app.models import Document, DocumentVersion

    settings = get_settings()
    doc = db.query(Document).filter(Document.slug == settings.document_slug).one_or_none()
    if not doc:
        return []
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number)
        .all()
    )
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "source_filename": v.source_filename,
            "created_at": v.created_at,
        }
        for v in versions
    ]
