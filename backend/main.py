"""
main.py

FastAPI application entry point.

Defines all API endpoints, configures CORS middleware, mounts the React
static build for production serving, and runs database initialisation on
startup. All business logic is delegated to orchestrator.py.
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env from the project root (one level above this file's backend/ directory).
# Must happen before any other imports that read environment variables.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import database
from . import orchestrator

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan: initialise the database on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs database initialisation before the app begins serving requests."""
    logger.info("Application starting up — initialising database.")
    database.init_db()
    logger.info("Database ready. Application is live.")
    yield
    logger.info("Application shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Reducto RAG Application",
    description="Financial document Q&A powered by Reducto, pgvector, and Vertex AI",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# Allow the React dev server (localhost:3000) in development.
# In production the frontend is served as static files by this same process,
# so the CORS policy is effectively a no-op for same-origin requests.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:8080",  # FastAPI itself (for local testing)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    message: str
    session_id: str


class QueryResponse(BaseModel):
    answer: str
    citations: list


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """
    Receives a PDF upload, deduplicates by content hash, and runs the
    document processing pipeline if the file has not been seen before.

    Returns:
        document_id, filename, and status ('processing' start, but pipeline
        runs synchronously so clients will see 'complete' or 'already_exists').
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    logger.info("Received upload: %s (session: %s)", file.filename, session_id)

    try:
        file_bytes = await file.read()
    except Exception:
        logger.exception("Failed to read uploaded file: %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to read uploaded file.")

    try:
        result = orchestrator.handle_upload(file_bytes, file.filename, session_id)
    except Exception:
        logger.exception("Document processing failed for: %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Document processing failed. Please try again.",
        )

    return {
        "document_id": result["document_id"],
        "filename": result["filename"],
        "status": result["status"],
    }


@app.post("/api/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """
    Receives the user's message and session_id, runs the agentic RAG pipeline,
    and returns the generated answer with source citations.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    logger.info(
        "Received query (session: %s): %.100s...", request.session_id, request.message
    )

    try:
        result = orchestrator.handle_message(request.message, request.session_id)
    except Exception:
        logger.exception("Query handling failed for session: %s", request.session_id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your question. Please try again.",
        )

    return {"answer": result["answer"], "citations": result["citations"]}


@app.get("/api/documents")
async def list_documents():
    """
    Returns all uploaded documents regardless of session. Documents are shared
    across all users and sessions.
    """
    try:
        docs = database.get_all_documents()
        # Serialise UUID and datetime fields to strings for JSON compatibility
        serialised = [
            {
                "document_id": str(d["document_id"]),
                "filename": d["filename"],
                "uploaded_at": d["uploaded_at"].isoformat() if d["uploaded_at"] else None,
                "status": d["status"],
            }
            for d in docs
        ]
        return {"documents": serialised}
    except Exception:
        logger.exception("Failed to retrieve document list.")
        raise HTTPException(status_code=500, detail="Failed to retrieve documents.")


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Hard-deletes a document and all its associated chunks (via ON DELETE CASCADE).
    """
    logger.info("Delete request for document_id: %s", document_id)

    try:
        deleted = database.delete_document(document_id)
    except Exception:
        logger.exception("Failed to delete document %s.", document_id)
        raise HTTPException(status_code=500, detail="Failed to delete document.")

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {"success": True, "document_id": document_id}


@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    """
    Returns all chat messages for the given session, ordered chronologically.
    Called by the frontend on page load to restore conversation state.
    """
    try:
        messages = database.get_chat_history(session_id)
        serialised = [
            {
                "role": m["role"],
                "content": m["content"],
                "created_at": m["created_at"].isoformat() if m.get("created_at") else None,
            }
            for m in messages
        ]
        return {"messages": serialised}
    except Exception:
        logger.exception("Failed to fetch history for session %s.", session_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve chat history.")


# ---------------------------------------------------------------------------
# Serve React static build in production
# ---------------------------------------------------------------------------

# The React build output is copied into /app/static during the Docker build.
# In development the React dev server runs separately on localhost:3000.
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    # Serve /assets, /static, etc. from the React build
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets"), html=False), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Catch-all route that serves index.html for all non-API paths, enabling
        client-side routing in the React SPA.
        """
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not found.")
