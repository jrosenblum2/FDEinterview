"""
orchestrator.py

Agentic orchestration layer. This module is the sole coordinator between
main.py and all other backend modules. It implements two public functions:

    handle_upload(file_bytes, filename, session_id)
        Runs the document processing pipeline: deduplication → Reducto parse
        → chunk embedding → database storage.

    handle_message(message, session_id)
        Runs the agentic RAG pipeline: intent classification → query embedding
        → chunk retrieval → sufficiency self-evaluation → answer generation.

The orchestrator never directly touches the database, Reducto API, Vertex AI,
or pgvector — it only calls functions exported from the other backend modules.
"""

import logging
from typing import Tuple

from . import database
from . import document_parser
from . import embeddings
from . import retrieval
from . import generation

logger = logging.getLogger(__name__)


def _classify_chunk_type(chunk: dict) -> str:
    """
    Inspects a chunk's metadata blocks to determine whether it is primarily
    a table, figure, or regular text.

    Returns one of: 'table', 'figure', or 'text'.
    """
    blocks = (chunk.get("metadata") or {}).get("blocks") or []
    types = [b.get("type", "") for b in blocks if isinstance(b, dict)]

    if not types:
        return "text"

    # If any block is a Table or Figure, treat the whole chunk as that type.
    # Table takes priority over Figure when both are present.
    if "Table" in types:
        return "table"
    if "Figure" in types:
        return "figure"
    return "text"


# Number of recent messages to pass as conversation context to Gemini
HISTORY_WINDOW = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_upload(file_bytes: bytes, filename: str, session_id: str) -> dict:
    """
    Orchestrates the full document processing pipeline for an uploaded PDF.

    Pipeline steps:
        1. MD5 hash + deduplication check (database)
        2. Reducto API parse → structured chunks
        3. Vertex AI embedding for each chunk
        4. Store chunks in the database and mark document 'complete'

    Args:
        file_bytes: Raw bytes of the uploaded PDF file.
        filename: Original filename of the PDF (used for display and logging).
        session_id: The frontend session UUID (reserved for future per-session
                    document scoping; not currently used in storage).

    Returns:
        A dict with keys:
            - document_id (str): UUID of the document record.
            - filename (str): Original filename.
            - status (str): 'already_exists' | 'complete'
              On any processing failure the document record is deleted and
              the exception is re-raised (no 'failed' status is persisted).
    """
    logger.info("handle_upload called for file: %s (session: %s)", filename, session_id)

    # -------------------------------------------------------------------------
    # Step 1 — Deduplication: hash the file and check the documents table
    # -------------------------------------------------------------------------
    content_hash = database.compute_md5(file_bytes)
    logger.info("Computed MD5 for %s: %s", filename, content_hash)

    existing = database.find_document_by_hash(content_hash)
    if existing:
        logger.info(
            "Document %s already exists (document_id=%s). Skipping processing.",
            filename,
            existing["document_id"],
        )
        return {
            "document_id": str(existing["document_id"]),
            "filename": existing["filename"],
            "status": "already_exists",
        }

    # Insert a new document record with status 'processing'
    document_id = database.insert_document(filename, content_hash)

    # -------------------------------------------------------------------------
    # Step 2 — Parse the document with the Reducto API
    # -------------------------------------------------------------------------
    try:
        logger.info("Calling Reducto for document_id=%s, file=%s", document_id, filename)
        raw_chunks = document_parser.parse_document(file_bytes, filename)
        logger.info("Reducto returned %d chunks for %s.", len(raw_chunks), filename)
    except Exception as exc:
        database.delete_document(document_id)
        logger.error(
            "Reducto parse failed for document_id=%s. Deleted document record.", document_id
        )
        raise

    # -------------------------------------------------------------------------
    # Step 3 — Embed all chunk texts in batches
    # -------------------------------------------------------------------------
    try:
        embed_texts = [chunk["embed"] for chunk in raw_chunks]
        logger.info(
            "Requesting embeddings for %d chunks (document_id=%s).",
            len(embed_texts),
            document_id,
        )
        vectors = embeddings.embed_chunks(embed_texts)
        logger.info("Received %d embedding vectors.", len(vectors))
    except Exception:
        database.delete_document(document_id)
        logger.error(
            "Embedding failed for document_id=%s. Deleted document record.", document_id
        )
        raise

    # -------------------------------------------------------------------------
    # Step 4 — Store chunks in the database and finalize the document status
    # -------------------------------------------------------------------------
    try:
        # Assemble chunk records combining Reducto output with embedding vectors
        chunk_records = []
        for idx, (chunk, vector) in enumerate(zip(raw_chunks, vectors)):
            chunk_records.append(
                {
                    "chunk_index": idx,
                    "chunk_text": chunk["content"],
                    "embed_text": chunk["embed"],
                    "embedding": vector,
                    "page_number": chunk.get("original_page"),
                    "metadata": chunk.get("metadata", {}),
                }
            )

        database.insert_chunks(document_id, chunk_records)
        database.update_document_status(document_id, "complete")
        logger.info(
            "Document processing complete: document_id=%s, chunks=%d",
            document_id,
            len(chunk_records),
        )
    except Exception:
        database.delete_document(document_id)
        logger.error(
            "Chunk storage failed for document_id=%s. Deleted document record.", document_id
        )
        raise

    return {
        "document_id": document_id,
        "filename": filename,
        "status": "complete",
    }


def handle_message(message: str, session_id: str) -> dict:
    """
    Orchestrates the agentic RAG pipeline for a user chat message.

    Pipeline steps:
        1. Fetch recent conversation history and list of uploaded documents
        2. Classify intent (query vs. out_of_scope) via Gemini; identify relevant documents
        3. [If query] Embed the refined query
        4. [If query] Retrieve top-K relevant chunks via pgvector, filtered to relevant documents
        5. [If query] Generate the final answer via Gemini — includes an internal sufficiency
           check; if the chunks are insufficient the model returns an explanation instead of
           an answer, and no citations are returned
        6. Persist both the user message and assistant reply to chat_history

    Args:
        message: The raw message text submitted by the user.
        session_id: The frontend session UUID for conversation isolation.

    Returns:
        A dict with keys:
            - answer (str): The assistant's response text.
            - citations (list): List of dicts, each with:
                  document_name (str), page_number (int|None), chunk_text (str)
    """
    logger.info("handle_message called (session: %s): %.100s...", session_id, message)

    # -------------------------------------------------------------------------
    # Step 1 — Load context: conversation history + uploaded document names
    # -------------------------------------------------------------------------
    history = database.get_chat_history(session_id, limit=HISTORY_WINDOW)
    all_documents = database.get_all_documents()
    document_names = [doc["filename"] for doc in all_documents]

    logger.info(
        "Context loaded: %d history messages, %d documents.",
        len(history),
        len(document_names),
    )

    # -------------------------------------------------------------------------
    # Step 2 — Intent classification
    # -------------------------------------------------------------------------
    intent_result = generation.classify_intent(message, document_names, history)
    intent = intent_result.get("intent", "out_of_scope")
    refined_query = intent_result.get("refined_query", message)
    relevant_documents = intent_result.get("relevant_documents") or []
    # Validate against actual document names — the LLM may hallucinate or
    # slightly mangle filenames, which would cause the SQL filter to match nothing.
    valid_names = set(document_names)
    relevant_documents = [d for d in relevant_documents if d in valid_names]
    # Fall back to all documents if none matched or LLM returned an empty list
    if not relevant_documents:
        relevant_documents = document_names

    logger.info("Intent classified as '%s'.", intent)
    logger.info("Relevant documents: %s", relevant_documents)

    if intent == "out_of_scope":
        # Return a canned response without running retrieval or generation
        out_of_scope_reply = (
            "I can only answer questions about the financial documents that have been "
            "uploaded to this application. Please upload a relevant PDF and ask a "
            "question about its contents."
        )
        # Persist the exchange so the user sees it in their history on reload
        database.save_message(session_id, "user", message)
        database.save_message(session_id, "assistant", out_of_scope_reply)
        return {"answer": out_of_scope_reply, "citations": []}

    # -------------------------------------------------------------------------
    # Step 3 — Embed the refined query
    # -------------------------------------------------------------------------
    logger.info("Embedding refined query: %.100s...", refined_query)
    query_vector = embeddings.embed_query(refined_query)

    # -------------------------------------------------------------------------
    # Step 4 — Retrieve top-K relevant chunks
    # -------------------------------------------------------------------------
    logger.info("Retrieving relevant chunks for query.")
    chunks = retrieval.retrieve_top_chunks(query_vector, document_names=relevant_documents)
    logger.info("Retrieved %d chunks.", len(chunks))

    if not chunks:
        # No chunks at all means no documents are indexed yet
        no_docs_reply = (
            "No documents have been uploaded yet, or none are fully processed. "
            "Please upload a financial document and try again."
        )
        database.save_message(session_id, "user", message)
        database.save_message(session_id, "assistant", no_docs_reply)
        return {"answer": no_docs_reply, "citations": []}

    # -------------------------------------------------------------------------
    # Step 5 — Generate the final answer (includes sufficiency self-evaluation)
    # -------------------------------------------------------------------------
    logger.info("Generating final answer.")
    generation_result = generation.generate_answer(refined_query, chunks, history)
    answer = generation_result["answer"]
    used_chunk_indices = generation_result["used_chunk_indices"]  # 1-based
    is_sufficient = generation_result.get("sufficient", True)
    logger.info("Answer generated. sufficient=%s, length=%d chars.", is_sufficient, len(answer))

    if not is_sufficient:
        database.save_message(session_id, "user", message)
        database.save_message(session_id, "assistant", answer)
        return {"answer": answer, "citations": []}

    # -------------------------------------------------------------------------
    # Step 7 — Persist messages and build citations
    # -------------------------------------------------------------------------
    database.save_message(session_id, "user", message)
    database.save_message(session_id, "assistant", answer)

    # Build citations only from chunks the model explicitly cited.
    # used_chunk_indices are 1-based; convert to 0-based for list indexing.
    # Fall back to all chunks if the model returned no indices (safety net).
    if used_chunk_indices:
        cited_chunks = [
            chunks[i - 1]
            for i in used_chunk_indices
            if isinstance(i, int) and 1 <= i <= len(chunks)
        ]
    else:
        cited_chunks = chunks

    cited_chunks = sorted(cited_chunks, key=lambda c: (c.get("page_number") is None, c.get("page_number")))

    citations = [
        {
            "document_name": chunk.get("filename", "Unknown"),
            "page_number": chunk.get("page_number"),
            "chunk_text": chunk.get("chunk_text", ""),
            "source_type": _classify_chunk_type(chunk),
        }
        for chunk in cited_chunks
    ]

    logger.info(
        "handle_message complete for session %s. %d/%d citations returned.",
        session_id,
        len(citations),
        len(chunks),
    )
    return {"answer": answer, "citations": citations}
