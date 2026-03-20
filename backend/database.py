"""
database.py

Handles all database connectivity, table initialization, and read/write operations
against Cloud SQL PostgreSQL. Exposes a single get_connection() function that returns
a valid connection regardless of whether the app is running locally (psycopg2 via the
Cloud SQL Auth Proxy) or in production (pg8000 via the Cloud SQL Python Connector).

Compatibility note: pg8000 (used in production) differs from psycopg2 in three ways
that affect this file:
  1. Cursors do not support the context manager protocol — use plain cur = conn.cursor()
  2. cursor_factory=RealDictCursor is not available — use _rows_to_dicts() instead
  3. psycopg2.extras.Json is not available — use json.dumps() instead
All functions in this file are written to work with both drivers.
"""

import os
import json
import logging
import hashlib
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


def get_connection():
    """
    Returns a database connection appropriate for the current environment.

    In development, connects via psycopg2 through the Cloud SQL Auth Proxy.
    In production, connects via pg8000 through the Cloud SQL Python Connector.

    Returns:
        A live database connection.
    """
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        from google.cloud.sql.connector import Connector

        connector = Connector()
        conn = connector.connect(
            os.getenv("INSTANCE_CONNECTION_NAME"),
            "pg8000",
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
        )
        return conn
    else:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        return conn


@contextmanager
def get_db_connection():
    """
    Context manager that yields a database connection and ensures it is closed
    after use. Rolls back on error.

    Yields:
        A database connection.
    """
    conn = None
    try:
        conn = get_connection()
        yield conn
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def _rows_to_dicts(cur) -> list:
    """
    Converts all rows returned by the cursor into a list of dicts keyed by
    column name. Works with both psycopg2 and pg8000 cursors.

    Args:
        cur: An executed cursor with results ready to fetch.

    Returns:
        List of dicts, one per row.
    """
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _row_to_dict(cur, row) -> Optional[dict]:
    """
    Converts a single row to a dict keyed by column name.

    Args:
        cur: The cursor that produced the row.
        row: A single row tuple, or None.

    Returns:
        A dict, or None if row is None.
    """
    if row is None:
        return None
    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def init_db():
    """
    Creates the required database tables if they do not already exist.
    Called once on application startup from main.py.

    Tables created:
        - documents: stores uploaded document metadata
        - chunks: stores parsed and embedded document chunks
        - chat_history: stores conversation messages per session
    """
    logger.info("Initializing database tables...")
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    filename TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT NOW(),
                    status TEXT DEFAULT 'processing'
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID REFERENCES documents(document_id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embed_text TEXT NOT NULL,
                    embedding vector(768),
                    page_number INTEGER,
                    metadata JSONB
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

            conn.commit()
        logger.info("Database tables initialized successfully.")
    except Exception:
        logger.exception("Failed to initialize database tables.")
        raise


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------

def find_document_by_hash(content_hash: str) -> Optional[dict]:
    """
    Looks up a document record by its MD5 content hash.

    Args:
        content_hash: MD5 hex digest of the file contents.

    Returns:
        A dict with document fields if found, otherwise None.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM documents WHERE content_hash = %s",
                (content_hash,),
            )
            return _row_to_dict(cur, cur.fetchone())
    except Exception:
        logger.exception("Error looking up document by hash: %s", content_hash)
        raise


def insert_document(filename: str, content_hash: str) -> str:
    """
    Inserts a new document record with status 'processing' and returns its UUID.

    Args:
        filename: Original filename of the uploaded PDF.
        content_hash: MD5 hex digest of the file contents.

    Returns:
        The newly created document_id as a string UUID.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO documents (filename, content_hash, status)
                VALUES (%s, %s, 'processing')
                RETURNING document_id
                """,
                (filename, content_hash),
            )
            document_id = str(cur.fetchone()[0])
            conn.commit()
            logger.info("Inserted document record: %s (%s)", filename, document_id)
            return document_id
    except Exception:
        logger.exception("Error inserting document: %s", filename)
        raise


def update_document_status(document_id: str, status: str):
    """
    Updates the status field of a document record.

    Args:
        document_id: UUID of the document to update.
        status: New status string (e.g. 'complete', 'failed').
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE documents SET status = %s WHERE document_id = %s",
                (status, document_id),
            )
            conn.commit()
            logger.info("Updated document %s status to '%s'.", document_id, status)
    except Exception:
        logger.exception("Error updating document status for %s.", document_id)
        raise


def get_all_documents() -> list:
    """
    Returns all document records ordered by upload time descending.

    Returns:
        List of dicts, each representing a document row.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT document_id, filename, uploaded_at, status FROM documents ORDER BY uploaded_at DESC"
            )
            return _rows_to_dicts(cur)
    except Exception:
        logger.exception("Error fetching all documents.")
        raise


def delete_document(document_id: str) -> bool:
    """
    Hard-deletes a document record. ON DELETE CASCADE removes associated chunks.

    Args:
        document_id: UUID of the document to delete.

    Returns:
        True if a row was deleted, False if no matching document was found.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM documents WHERE document_id = %s",
                (document_id,),
            )
            deleted = cur.rowcount > 0
            conn.commit()
            if deleted:
                logger.info("Deleted document %s and cascaded chunks.", document_id)
            else:
                logger.warning("No document found with id %s.", document_id)
            return deleted
    except Exception:
        logger.exception("Error deleting document %s.", document_id)
        raise


# ---------------------------------------------------------------------------
# Chunk operations
# ---------------------------------------------------------------------------

def insert_chunks(document_id: str, chunks: list):
    """
    Bulk-inserts chunk records for a document into the chunks table.

    Each item in chunks should be a dict with keys:
        chunk_index, chunk_text, embed_text, embedding, page_number, metadata

    Args:
        document_id: UUID of the parent document.
        chunks: List of chunk dicts prepared by the orchestrator.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            for chunk in chunks:
                cur.execute(
                    """
                    INSERT INTO chunks
                        (document_id, chunk_index, chunk_text, embed_text,
                         embedding, page_number, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        chunk["chunk_index"],
                        chunk["chunk_text"],
                        chunk["embed_text"],
                        "[" + ",".join(str(v) for v in chunk["embedding"]) + "]",
                        chunk.get("page_number"),
                        json.dumps(chunk.get("metadata", {})),
                    ),
                )
            conn.commit()
            logger.info(
                "Inserted %d chunks for document %s.", len(chunks), document_id
            )
    except Exception:
        logger.exception("Error inserting chunks for document %s.", document_id)
        raise


# ---------------------------------------------------------------------------
# Chat history operations
# ---------------------------------------------------------------------------

def save_message(session_id: str, role: str, content: str):
    """
    Persists a single chat message to the chat_history table.

    Args:
        session_id: The browser session UUID for this conversation.
        role: Either 'user' or 'assistant'.
        content: The text of the message.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO chat_history (session_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (session_id, role, content),
            )
            conn.commit()
    except Exception:
        logger.exception("Error saving message for session %s.", session_id)
        raise


def get_chat_history(session_id: str, limit: int = None) -> list:
    """
    Retrieves chat messages for a given session, ordered by creation time ascending.

    Args:
        session_id: The session UUID to filter by.
        limit: Optional maximum number of most-recent messages to return.

    Returns:
        List of dicts with keys: role, content, created_at.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            if limit:
                # Fetch the N most recent messages, then re-order ascending
                cur.execute(
                    """
                    SELECT role, content, created_at FROM (
                        SELECT role, content, created_at
                        FROM chat_history
                        WHERE session_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    ) sub
                    ORDER BY created_at ASC
                    """,
                    (session_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_history
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
            return _rows_to_dicts(cur)
    except Exception:
        logger.exception("Error fetching chat history for session %s.", session_id)
        raise


def compute_md5(file_bytes: bytes) -> str:
    """
    Computes the MD5 hex digest of a byte string.

    Args:
        file_bytes: Raw bytes of the uploaded file.

    Returns:
        Lowercase hex MD5 string.
    """
    return hashlib.md5(file_bytes).hexdigest()
