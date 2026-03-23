"""
document_parser.py

Handles all Reducto API interactions. Sends uploaded PDFs to Reducto for
structured parsing and returns the resulting chunks for downstream embedding
and storage.

Note: the PyPI package is `reductoai` — the unrelated `reducto` package is a
Python code stats tool and must not be used here.

The pipeline always returns results as a URL (result.parse.result.type == "url").
We fetch that URL to get the full parse result containing the chunk list.
"""

import io
import os
import json
import logging
import urllib.request

from reducto import Reducto

logger = logging.getLogger(__name__)


def parse_document(file_bytes: bytes, filename: str) -> list:
    """
    Sends a PDF to a Reducto pipeline for synchronous parsing and returns
    a list of structured chunks.

    Each returned chunk is a dict with the following keys:
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
        Exception: Re-raises any Reducto API or fetch error after logging it.
    """
    api_key = os.getenv("REDUCTO_API_KEY")
    if not api_key:
        raise ValueError("REDUCTO_API_KEY environment variable is not set.")

    PIPELINE_ID = "k97fcj9vc7mnbsdj9yz3nawr5983dmn8"

    client = Reducto(api_key=api_key)

    logger.info("Starting Reducto parse for document: %s", filename)

    try:
        file_obj = io.BytesIO(file_bytes)
        file_obj.name = filename
        upload = client.upload(file=file_obj)

        response = client.pipeline.run(
            input=upload,
            pipeline_id=PIPELINE_ID,
        )
    except Exception:
        logger.exception("Reducto API call failed for document: %s", filename)
        raise

    logger.info("Reducto pipeline call completed for %s. Fetching result URL.", filename)

    try:
        chunks = _extract_chunks(response)
    except Exception:
        logger.exception("Failed to extract chunks from Reducto response for %s.", filename)
        raise

    logger.info("Extracted %d chunks from %s.", len(chunks), filename)
    return chunks


def _extract_chunks(response) -> list:
    """
    Extracts chunks from a Reducto pipeline response.

    The pipeline always returns results via a URL:
        response.result.parse.result.type == "url"
        response.result.parse.result.url  -> fetch -> { "chunks": [...] }

    Args:
        response: The Reducto PipelineResponse object.

    Returns:
        List of normalised chunk dicts.
    """
    # Deserialise to a plain dict to avoid Pydantic field declaration gaps
    if hasattr(response, "model_dump"):
        response_dict = response.model_dump()
    elif isinstance(response, dict):
        response_dict = response
    else:
        response_dict = vars(response) if hasattr(response, "__dict__") else {}

    parse_result = (
        (response_dict.get("result") or {})
        .get("parse") or {}
    ).get("result") or {}

    result_type = parse_result.get("type")
    result_url = parse_result.get("url")

    if result_type != "url" or not result_url:
        raise ValueError(
            f"Expected pipeline result type 'url' with a URL, got type={result_type!r}, url={result_url!r}"
        )

    logger.info("Fetching Reducto result from URL.")
    with urllib.request.urlopen(result_url) as resp:
        full_result = json.loads(resp.read().decode("utf-8"))

    raw_chunks = full_result.get("chunks") or []
    logger.info("Fetched %d raw chunks from result URL.", len(raw_chunks))

    chunks = []
    for raw in raw_chunks:
        if not isinstance(raw, dict):
            raw = vars(raw) if hasattr(raw, "__dict__") else {}

        content = raw.get("content", "")
        embed = raw.get("embed", content)
        metadata = {k: v for k, v in raw.items() if k not in ("content", "embed")}

        original_page = None
        blocks = raw.get("blocks") or []
        if blocks:
            first_bbox = blocks[0].get("bbox", {})
            original_page = first_bbox.get("original_page") or first_bbox.get("page")

        chunks.append({
            "content": content,
            "embed": embed,
            "original_page": original_page,
            "metadata": metadata,
        })

    return chunks
