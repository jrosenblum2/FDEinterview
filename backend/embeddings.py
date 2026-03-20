"""
embeddings.py

Wraps Vertex AI gemini-embedding-001 calls for generating 768-dimensional
embedding vectors. Used at upload time to embed document chunks, and at
query time to embed the user's refined query.
"""

import os
import logging
from typing import List

import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

logger = logging.getLogger(__name__)

# Vertex AI embedding model name as specified in the project requirements
EMBEDDING_MODEL_NAME = "gemini-embedding-001"

# Maximum number of texts to embed in a single API call.
# Vertex AI has per-request limits; batching avoids per-chunk latency.
EMBED_BATCH_SIZE = 250


def _get_embedding_model() -> TextEmbeddingModel:
    """
    Initialises the Vertex AI SDK and returns the embedding model client.

    Vertex AI authentication is handled automatically:
    - Locally: via gcloud application default credentials
    - In production: via the Cloud Run service account

    Returns:
        A TextEmbeddingModel instance ready for inference calls.
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    region = os.getenv("GCP_REGION", "us-central1")

    if not project_id:
        raise ValueError("GCP_PROJECT_ID environment variable is not set.")

    vertexai.init(project=project_id, location=region)
    return TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL_NAME)


def embed_chunks(texts: List[str]) -> List[List[float]]:
    """
    Generates embedding vectors for a list of texts in batches.

    Used at document upload time to embed the `embed` field of each Reducto chunk.

    Args:
        texts: List of strings to embed (should be the `embed` field from Reducto).

    Returns:
        List of 768-dimensional float vectors, one per input text, in the same order.

    Raises:
        Exception: Re-raises any Vertex AI error after logging.
    """
    if not texts:
        return []

    logger.info("Embedding %d chunks via Vertex AI gemini-embedding-001.", len(texts))

    try:
        model = _get_embedding_model()
        all_embeddings = []

        # Process in batches to stay within Vertex AI per-request limits
        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[batch_start : batch_start + EMBED_BATCH_SIZE]

            # Wrap each text in a TextEmbeddingInput for the model
            inputs = [TextEmbeddingInput(text=t, task_type="RETRIEVAL_DOCUMENT") for t in batch]
            # gemini-embedding-001 defaults to 3072 dimensions; request 768 explicitly
            # to match the vector(768) column definition in the chunks table.
            results = model.get_embeddings(inputs, output_dimensionality=768)

            for result in results:
                all_embeddings.append(result.values)

            logger.info(
                "Embedded batch %d–%d of %d.",
                batch_start + 1,
                batch_start + len(batch),
                len(texts),
            )

        logger.info("Chunk embedding complete. %d vectors generated.", len(all_embeddings))
        return all_embeddings

    except Exception:
        logger.exception("Vertex AI embedding call failed for chunk batch.")
        raise


def embed_query(query_text: str) -> List[float]:
    """
    Generates a single embedding vector for a user query string.

    Uses RETRIEVAL_QUERY task type so the vector is optimised for similarity
    search against RETRIEVAL_DOCUMENT vectors stored in pgvector.

    Args:
        query_text: The user's refined query string.

    Returns:
        A 768-dimensional float vector.

    Raises:
        Exception: Re-raises any Vertex AI error after logging.
    """
    logger.info("Embedding query via Vertex AI gemini-embedding-001.")

    try:
        model = _get_embedding_model()
        inputs = [TextEmbeddingInput(text=query_text, task_type="RETRIEVAL_QUERY")]
        results = model.get_embeddings(inputs, output_dimensionality=768)
        vector = results[0].values
        logger.info("Query embedding complete. Vector dimension: %d.", len(vector))
        return vector

    except Exception:
        logger.exception("Vertex AI embedding call failed for query: %s", query_text)
        raise
