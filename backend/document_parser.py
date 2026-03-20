"""
document_parser.py

Handles all Reducto API interactions. Sends uploaded PDFs to Reducto for
structured parsing and returns the resulting chunks for downstream embedding
and storage.

Note: the PyPI package is `reductoai` — the unrelated `reducto` package is a
Python code stats tool and must not be used here.
"""

import io
import os
import logging

from reducto import Reducto

logger = logging.getLogger(__name__)


def parse_document(file_bytes: bytes, filename: str) -> list:
    """
    Sends a PDF to the Reducto API for synchronous parsing and returns
    a list of structured chunks.

    Each returned chunk is a dict with the following keys extracted from
    Reducto's response:
        - content (str): Human-readable text of the chunk, used as LLM context.
        - embed (str): Text optimized for embedding generation.
        - original_page (int | None): Page number the chunk appears on.
        - metadata (dict): All remaining Reducto chunk fields stored as-is.

    Args:
        file_bytes: Raw bytes of the uploaded PDF file.
        filename: Original filename, used for logging.

    Returns:
        List of chunk dicts ready for embedding and storage.

    Raises:
        Exception: Re-raises any Reducto API error after logging it.
    """
    api_key = os.getenv("REDUCTO_API_KEY")
    if not api_key:
        raise ValueError("REDUCTO_API_KEY environment variable is not set.")

    # The client automatically uses REDUCTO_API_KEY if no api_key is passed,
    # but we pass it explicitly for clarity.
    client = Reducto(api_key=api_key)

    logger.info("Starting Reducto parse for document: %s", filename)

    try:
        # Upload the file bytes first, then run parsing on the uploaded file.
        # The SDK requires a file-like object for upload.
        file_obj = io.BytesIO(file_bytes)
        file_obj.name = filename  # Some SDK versions use the name for content-type detection
        upload = client.upload(file=file_obj)

        # Run synchronous parsing with chunking and figure summarization enabled.
        # filter_blocks removes navigational noise (headers, footers, page numbers)
        # that would pollute chunk text.
        # `input` accepts the Upload object returned by client.upload().
        response = client.parse.run(
            input=upload,
            retrieval={
                "chunking": {"chunk_mode": "variable"},
                "filter_blocks": ["Header", "Footer", "Page Number"],
            },
            enhance={
                "summarize_figures": True,
            },
        )
    except Exception:
        logger.exception("Reducto API call failed for document: %s", filename)
        raise

    logger.info(
        "Reducto parse completed for %s. Extracting chunks from response.", filename
    )

    chunks = _extract_chunks(response)
    logger.info("Extracted %d chunks from %s.", len(chunks), filename)
    return chunks


def _extract_chunks(response) -> list:
    """
    Normalises the Reducto API response into a flat list of chunk dicts.

    Reducto returns a result object whose structure contains a list of chunks.
    This function walks that structure and extracts the fields we need while
    preserving all remaining metadata for storage.

    Args:
        response: The raw Reducto API response object.

    Returns:
        List of normalised chunk dicts.
    """
    chunks = []

    # The Reducto response structure: response.result.chunks is the list of chunks.
    # Each chunk has: content, embed, and metadata (which contains original_page, etc.)
    raw_chunks = []

    if hasattr(response, "result") and hasattr(response.result, "chunks"):
        raw_chunks = response.result.chunks
    elif hasattr(response, "chunks"):
        raw_chunks = response.chunks
    else:
        result = response if isinstance(response, dict) else vars(response)
        raw_chunks = result.get("result", {}).get("chunks", [])

    for raw in raw_chunks:
        # Normalise to a plain dict for uniform access and JSON serialisability.
        # The SDK returns Pydantic BaseModel objects; model_dump() recursively
        # converts them (and any nested models) to plain Python dicts/lists,
        # which psycopg2's Json adapter can serialize for the JSONB column.
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        elif not isinstance(raw, dict):
            raw = vars(raw) if hasattr(raw, "__dict__") else {}

        content = raw.get("content", "")
        embed = raw.get("embed", content)  # Fall back to content if embed is absent

        # Metadata is everything in the chunk except content and embed
        metadata = {k: v for k, v in raw.items() if k not in ("content", "embed")}

        # Page number lives on the first block's bounding box, not on the chunk itself.
        # blocks[0].bbox.page is 1-indexed. We use original_page if present (some
        # documents have a page offset), otherwise fall back to page.
        original_page = None
        blocks = raw.get("blocks") or []
        if blocks:
            first_bbox = blocks[0].get("bbox", {})
            original_page = first_bbox.get("original_page") or first_bbox.get("page")

        chunks.append(
            {
                "content": content,
                "embed": embed,
                "original_page": original_page,
                "metadata": metadata,
            }
        )

    return chunks
