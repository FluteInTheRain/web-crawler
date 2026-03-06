"""
FastAPI query service.

Endpoints
---------
GET  /health          Liveness check (no external calls).
POST /query           Answer a question using the RAG engine.

Start locally:
    uvicorn src.api:app --reload

On Render the start command is set in render.yaml.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.rag_engine import create_rag_engine

# ---------------------------------------------------------------------------
# App lifecycle — build the engine once at startup, reuse for every request
# ---------------------------------------------------------------------------

_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    try:
        _engine = create_rag_engine()
    except RuntimeError as exc:
        # Surface missing-key errors immediately instead of failing per request
        raise RuntimeError(f"Failed to initialise RAG engine: {exc}") from exc
    yield
    _engine = None


app = FastAPI(
    title="Web-Crawler RAG API",
    description="Ask questions against the crawled knowledge base.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural-language question")
    n_results: int = Field(4, ge=1, le=20, description="Source chunks to retrieve")


class Source(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
def health():
    """Return 200 when the service is up."""
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse, tags=["rag"])
def query(req: QueryRequest):
    """
    Answer a question using the RAG pipeline.

    Retrieves the *n_results* most relevant chunks from Qdrant, then calls
    the configured OpenAI model to produce a cited answer.
    """
    if _engine is None:
        raise HTTPException(status_code=503, detail="Engine not ready")

    try:
        result = _engine(req.question, n_results=req.n_results)
        return QueryResponse(answer=result["answer"], sources=result["sources"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
