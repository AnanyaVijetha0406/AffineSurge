from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import browse, documents, generations, selections


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CT-200 QA Traceability API",
    description="Document tree, versioning, selections, LLM test-case generation, and staleness detection.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(documents.router)
app.include_router(browse.router)
app.include_router(selections.router)
app.include_router(generations.router)


@app.get("/health")
def health():
    from app.store import get_generation_store

    store = get_generation_store()
    return {"status": "ok", "generation_store": store.backend}
