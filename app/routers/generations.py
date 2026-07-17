from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.store import get_generation_store
from app.schemas import GenerateRequest, GenerationResponse, StalenessReport
from app.services.generation import assess_staleness, generate_for_selection

router = APIRouter(tags=["generations"])


def _to_response(doc: dict, stale_info: dict | None = None) -> GenerationResponse:
    created = doc["created_at"]
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return GenerationResponse(
        id=str(doc["id"]),
        selection_id=doc["selection_id"],
        selection_name=doc["selection_name"],
        created_at=created,
        test_cases=doc["test_cases"],
        source_hashes=doc["source_hashes"],
        llm_status=doc["llm_status"],
        stale=None if stale_info is None else stale_info["is_stale"],
        staleness_detail=stale_info,
    )


@router.post("/generate", response_model=GenerationResponse)
def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    """Policy: same selection returns cached generation unless force=true."""
    try:
        doc = generate_for_selection(db, req.selection_id, force=req.force)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    stale_info = assess_staleness(db, doc)
    return _to_response(doc, stale_info)


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
def get_generation(generation_id: str, db: Session = Depends(get_db)):
    doc = get_generation_store().find_one({"_id": generation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Generation not found")
    doc["id"] = str(doc["_id"])
    stale_info = assess_staleness(db, doc)
    return _to_response(doc, stale_info)


@router.get("/generations", response_model=list[GenerationResponse])
def list_generations(
    selection_id: int | None = None,
    node_id: int | None = None,
    db: Session = Depends(get_db),
):
    query: dict = {}
    if selection_id is not None:
        query["selection_id"] = selection_id
    if node_id is not None:
        query["source_nodes.node_id"] = node_id

    docs = get_generation_store().find(query, limit=50)
    out = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        stale_info = assess_staleness(db, doc)
        out.append(_to_response(doc, stale_info))
    return out


@router.get("/generations/{generation_id}/staleness", response_model=StalenessReport)
def generation_staleness(generation_id: str, db: Session = Depends(get_db)):
    doc = get_generation_store().find_one({"_id": generation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Generation not found")
    doc["id"] = str(doc["_id"])
    report = assess_staleness(db, doc)
    return StalenessReport(**report)
