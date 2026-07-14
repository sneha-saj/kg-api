"""
Minimal FastAPI server around a maplib in-memory knowledge graph.

Endpoints:
  POST /upload         - upload a .ttl file, merges it into the graph
  POST /sparql          - run a SPARQL query, get JSON rows back
  GET  /sparql?query=.. - same, for quick testing / Yasgui-style tools
  GET  /health           - loaded graph count, for sanity checking

Run:
  uvicorn app.main:app --reload --workers 1
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import KnowledgeGraphStore
from .resolvers import get_concerts

ASSERTIONS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "assertions"
ASSERTIONS_DIR.mkdir(parents=True, exist_ok=True)

store = KnowledgeGraphStore(ASSERTIONS_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loaded = store.reload_all_from_disk()
    print(f"[startup] loaded {loaded} .ttl file(s) from {ASSERTIONS_DIR}")
    yield


app = FastAPI(title="Knowledge Graph API", lifespan=lifespan)

# Wide open for now so the frontend dev can hit this from localhost/any origin.
# Tighten allow_origins to your actual frontend URL before this goes anywhere near prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "assertions_dir": str(ASSERTIONS_DIR)}


@app.post("/upload")
async def upload_ttl(file: UploadFile = File(...)):
    if not file.filename.endswith(".ttl"):
        raise HTTPException(400, "Only .ttl files are accepted")

    content = await file.read()
    try:
        total_files = store.upload_ttl(file.filename, content)
    except Exception as e:
        # maplib raises MaplibException on parse errors (bad Turtle syntax etc.)
        raise HTTPException(422, f"Failed to load {file.filename}: {e}")

    return {"filename": file.filename, "status": "loaded", "total_files_loaded": total_files}


@app.get("/concerts")
def concerts():
    """Shaped endpoint: nested JSON, no SPARQL knowledge needed by the caller."""
    return get_concerts(store)


class SparqlRequest(BaseModel):
    query: str


def _run_query_to_json(sparql: str):
    try:
        result = store.query(sparql)
    except Exception as e:
        raise HTTPException(400, f"SPARQL error: {e}")

    # SELECT queries come back as a Polars DataFrame -> list of plain dicts,
    # which FastAPI serialises to JSON directly. CONSTRUCT/ASK results are
    # returned as-is (str(result) as a fallback) since the frontend use case
    # here is SELECT queries for the UI.
    if hasattr(result, "to_dicts"):
        return {"rows": result.to_dicts()}
    return {"result": str(result)}


@app.post("/sparql")
def sparql_post(body: SparqlRequest):
    return _run_query_to_json(body.query)


@app.get("/sparql")
def sparql_get(query: Optional[str] = None):
    if not query:
        raise HTTPException(400, "Missing ?query=")
    return _run_query_to_json(query)