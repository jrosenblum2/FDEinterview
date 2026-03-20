"""
generation.py

All Vertex AI Gemini generative calls using gemini-2.5-flash.

Three distinct generative functions are exposed:
  1. classify_intent      – determines whether the user's message is a document
                            query or out of scope.
  2. evaluate_sufficiency – checks whether the retrieved chunks contain enough
                            information to answer the user's question.
  3. generate_answer      – produces the final answer grounded in the retrieved
                            chunks and conversation history.

All system prompts are intentionally left as TODO placeholders per the project
spec — do not fill them in without explicit instruction.
"""

import os
import json
import logging
from typing import List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

logger = logging.getLogger(__name__)

GENERATION_MODEL_NAME = "gemini-2.5-flash"


def _get_generative_model() -> GenerativeModel:
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
    return GenerativeModel(GENERATION_MODEL_NAME)


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

    Raises:
        Exception: Re-raises any Vertex AI or JSON parsing error after logging.
    """
    logger.info("Classifying intent for message: %.100s...", user_message)

    # TODO: refine intent classification prompt
    system_prompt = """You are an intent classification assistant for a financial document Q&A application.
Classify the user's intent and return a JSON object only."""

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

Recent conversation:
{history_text}

User message: {user_message}

Classify the intent and return ONLY a JSON object with no preamble or markdown:
{{
  "intent": "query" or "out_of_scope",
  "refined_query": "the user's question, cleaned up and made more precise if needed"
}}"""

    try:
        model = _get_generative_model()
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


def evaluate_sufficiency(
    refined_query: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    Uses Gemini to determine whether the retrieved chunks contain enough
    information to confidently answer the refined query.

    Args:
        refined_query: The cleaned-up user question from classify_intent().
        retrieved_chunks: List of chunk dicts returned by retrieval.retrieve_top_chunks().

    Returns:
        A dict with keys:
            - sufficient (bool): True if the chunks are sufficient.
            - reason (str): Brief explanation of the decision.

    Raises:
        Exception: Re-raises any Vertex AI or JSON parsing error after logging.
    """
    logger.info("Evaluating chunk sufficiency for query: %.100s...", refined_query)

    # TODO: refine sufficiency evaluation prompt
    system_prompt = """You are a quality evaluator for a financial document Q&A system.
Determine whether the provided document chunks contain enough information to answer the question.
Return a JSON object only."""

    # Format chunks for the model
    chunks_text = "\n\n".join(
        f"[Chunk {i+1} from '{c.get('filename', 'unknown')}', page {c.get('page_number', '?')}]:\n{c.get('chunk_text', '')}"
        for i, c in enumerate(retrieved_chunks)
    )

    user_prompt = f"""Question: {refined_query}

Retrieved document chunks:
{chunks_text}

Return ONLY a JSON object with no preamble or markdown:
{{
  "sufficient": true or false,
  "reason": "brief explanation"
}}"""

    try:
        model = _get_generative_model()
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw_text = response.text.strip()
        result = json.loads(raw_text)
        logger.info(
            "Sufficiency evaluation result: sufficient=%s, reason=%s",
            result.get("sufficient"),
            result.get("reason"),
        )
        return result
    except Exception:
        logger.exception("Sufficiency evaluation failed.")
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

    # TODO: refine answer generation prompt
    system_prompt = """You are a helpful financial document assistant.
Answer the user's question accurately based only on the provided numbered document excerpts.
Return a JSON object only — no preamble, no markdown fences."""

    # Number the chunks explicitly so the model can reference them by index
    chunks_text = "\n\n".join(
        f"[Chunk {i+1} | Source: '{c.get('filename', 'unknown')}', Page {c.get('page_number', '?')}]:\n{c.get('chunk_text', '')}"
        for i, c in enumerate(retrieved_chunks)
    )

    # Format recent conversation history for continuity
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
  "answer": "your answer in markdown format",
  "used_chunk_indices": [list of chunk numbers (1-based) that you actually used to write the answer]
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
        logger.info(
            "Answer generation complete. Length: %d chars. Used chunks: %s",
            len(answer),
            used_indices,
        )
        return {"answer": answer, "used_chunk_indices": used_indices}
    except Exception:
        logger.exception("Answer generation failed.")
        raise
