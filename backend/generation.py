"""
generation.py

Vertex AI Gemini generative calls. Two models are used:
  - gemini-2.5-flash-lite: classify_intent (fast, cheap — used for classification)
  - gemini-2.5-flash:      generate_answer (highest quality for final response)

Two distinct generative functions are exposed:
  1. classify_intent  – determines whether the user's message is a document query
                        or out of scope, refines the query for RAG retrieval, and
                        identifies which uploaded documents are most likely relevant.
  2. generate_answer  – evaluates whether the retrieved chunks are sufficient to
                        answer the question, then either generates a grounded answer
                        or explains why the documents cannot answer it. Both
                        sufficiency evaluation and answer generation happen in a
                        single LLM call to minimise latency and API cost.
"""

import os
import json
import logging
from typing import List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

logger = logging.getLogger(__name__)

LITE_MODEL_NAME = "gemini-2.5-flash-lite"
GENERATION_MODEL_NAME = "gemini-2.5-flash"


def _get_generative_model(model_name: str = GENERATION_MODEL_NAME) -> GenerativeModel:
    """
    Initialises Vertex AI and returns a GenerativeModel instance.

    Authentication is automatic (ADC locally, service account in Cloud Run).

    Returns:
        A GenerativeModel ready for generate_content() calls.
    """
    project_id = os.getenv("GCP_PROJECT_ID")
    region = os.getenv("GCP_REGION", "us-central1")

    if not project_id:
        raise ValueError("GCP_PROJECT_ID environment variable is not set.")

    vertexai.init(project=project_id, location=region)
    return GenerativeModel(model_name)


def classify_intent(
    user_message: str,
    document_names: List[str],
    conversation_history: List[dict],
) -> dict:
    """
    Uses Gemini to classify the user's intent as either 'query' or 'out_of_scope',
    and returns a cleaned-up version of the user's question as refined_query.

    Args:
        user_message: The raw message submitted by the user.
        document_names: List of filenames currently uploaded in the system.
        conversation_history: Last N messages from chat_history for context.

    Returns:
        A dict with keys:
            - intent (str): 'query' or 'out_of_scope'
            - refined_query (str): The cleaned-up version of the user's question.
            - relevant_documents (list): The documents deemed to be most relevant to the user's query to improve retrieval

    Raises:
        Exception: Re-raises any Vertex AI or JSON parsing error after logging.
    """
    logger.info("Classifying intent for message: %.100s...", user_message)

    # Intent classification and query enhancement prompt
    system_prompt = """You are an intent classification and query enhancing assistant for a financial document Q&A application.
    Classify the intent and return a JSON object only. The intent should be 'query' if the question that can be answered by the 
    uploaded documents, and 'out_of_scope' if they are making a statement, asking for general advice, or anything that cannot be 
    answered by the documents alone.

    Also return a cleaned-up version of the question as refined_query. refined_query will be used for a
    RAG retrieval, so if the intent is 'query', make sure to enhance the question with any relevant context
    from the conversation history and relevant uploaded document names. The goal is to make the query as effective
    as possible for RAG retrieval, so if it is vague, make it more specific and include the key words that are likely
    to retrieve the most relevant chunks from the RAG database. If the intent is 'out_of_scope', refined_query
    should just be an empty string.

    Also return relevant_documents: a list of filenames from the uploaded documents list that are most likely
    to contain the answer to the user's question. Only include documents that are genuinely relevant — if the
    question is clearly about a specific document or fund, exclude unrelated ones. If the question is broad or
    could span multiple documents, include all of them. If the intent is 'out_of_scope', return an empty list.
    The filenames must exactly match the names in the uploaded documents list.

    Use the conversation history and list of uploaded document names to inform your classification of the query,
    but do not reference them directly in your answer. Return ONLY a JSON object with no preamble
    or markdown, in the following format:
    {
    "intent": "query" or "out_of_scope",
    "refined_query": "the question, cleaned up and made more precise if needed",
    "relevant_documents": ["filename1.pdf", "filename2.pdf"]
    }
    """

    # Build a context string from the recent conversation history
    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in conversation_history
    )

    documents_text = (
        "\n".join(f"- {name}" for name in document_names)
        if document_names
        else "(no documents uploaded)"
    )

    user_prompt = f"""Uploaded documents:
    {documents_text}

    Recent conversation history:
    {history_text}

    User message: {user_message}

    Classify the intent and return ONLY a JSON object with no preamble or markdown:
    {{
    "intent": "query" or "out_of_scope",
    "refined_query": "the question, cleaned up and made more precise if needed",
    "relevant_documents": ["filename1.pdf", "filename2.pdf"]
    }}"""

    try:
        model = _get_generative_model(LITE_MODEL_NAME)
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=GenerationConfig(
                temperature=0.0,  # Deterministic for classification
                response_mime_type="application/json",
            ),
        )
        raw_text = response.text.strip()
        result = json.loads(raw_text)
        logger.info("Intent classification result: intent=%s", result.get("intent"))
        return result
    except Exception:
        logger.exception("Intent classification failed.")
        raise


def generate_answer(
    refined_query: str,
    retrieved_chunks: List[dict],
    conversation_history: List[dict],
) -> dict:
    """
    Uses Gemini to generate a complete, grounded answer to the user's query
    based on the retrieved document chunks and recent conversation context.

    The model is instructed to return JSON containing the answer text AND the
    1-based indices of the chunks it actually drew on. This allows the caller
    to surface only the citations that genuinely informed the response.

    Args:
        refined_query: The cleaned-up user question from classify_intent().
        retrieved_chunks: Top-K chunk dicts from retrieval.retrieve_top_chunks().
        conversation_history: Last N messages from chat_history for conversational context.

    Returns:
        A dict with keys:
            - answer (str): The generated answer in markdown.
            - used_chunk_indices (list[int]): 1-based indices of chunks used.

    Raises:
        Exception: Re-raises any Vertex AI error after logging.
    """
    logger.info("Generating answer for query: %.100s...", refined_query)

    system_prompt = """You are a helpful, honest financial document assistant.

    First, decide whether the provided numbered document excerpts contain enough information
    to confidently answer the question. Set "sufficient" to true or false accordingly.

    If sufficient is true:
    - Answer the question accurately based only on the excerpts. Do not hallucinate.
    - Keep the answer concise but complete. After answering, briefly suggest related questions
      you could answer based on the excerpts.
    - Return the 1-based indices of the chunks you actually used in used_chunk_indices.
    - DO NOT refer to specific chunks by number in your answer text.

    If sufficient is false:
    - Explain briefly why the excerpts do not contain enough information to answer the question.
    - Suggest specific related questions you could answer based on what the excerpts do contain.
    - Set used_chunk_indices to an empty list.

    Return a JSON object only — no preamble, no markdown fences."""

    chunks_text = "\n\n".join(
        f"[Chunk {i+1} | Source: '{c.get('filename', 'unknown')}', Page {c.get('page_number', '?')}]:\n{c.get('chunk_text', '')}"
        for i, c in enumerate(retrieved_chunks)
    )

    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in conversation_history
    )

    user_prompt = f"""Recent conversation:
    {history_text}

    Numbered document excerpts:
    {chunks_text}

    Question: {refined_query}

    Return ONLY a JSON object with no preamble or markdown:
    {{
    "sufficient": true or false,
    "answer": "your answer or insufficiency explanation in markdown format",
    "used_chunk_indices": [1-based indices of chunks used, or empty list if insufficient]
    }}"""

    try:
        model = _get_generative_model()
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        result = json.loads(response.text.strip())
        answer = result.get("answer", "")
        used_indices = result.get("used_chunk_indices", [])
        sufficient = result.get("sufficient", True)
        logger.info(
            "Answer generation complete. sufficient=%s, length=%d chars, used chunks: %s",
            sufficient,
            len(answer),
            used_indices,
        )
        return {"answer": answer, "used_chunk_indices": used_indices, "sufficient": sufficient}
    except Exception:
        logger.exception("Answer generation failed.")
        raise
