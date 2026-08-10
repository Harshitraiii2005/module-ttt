"""Builds a prompt from matched query elements and summarizes them via the LLM.

Kept separate from app.core.llm so that llm.py stays a generic,
provider-agnostic "send a prompt, get text back" client, while the
query-specific prompt shape lives here.
"""

from typing import Any, Dict, List, Optional

from app.core.llm import get_llm_response

# Cap how much matched content we feed the model. Elements are already
# ranked by relevance, so truncating just drops the lowest-scoring tail.
MAX_ELEMENTS = 20
MAX_CHARS_PER_ELEMENT = 2000


def _build_prompt(query: str, elements: List[Dict[str, Any]]) -> str:
    chunks = []
    for i, element in enumerate(elements[:MAX_ELEMENTS], start=1):
        content = (element.get("content") or "").strip()
        if not content:
            continue
        chunks.append(content[:MAX_CHARS_PER_ELEMENT])

    joined = "\n\n".join(f"[{i}] {chunk}" for i, chunk in enumerate(chunks, start=1))
    return (f"""
        You are a document assistant. Answer the user's question using ONLY the provided document excerpts.

    Question: ${query}

    Relevant document excerpts: ${joined}

    ## Quick Answer
    Write 1–3 plain-English sentences that directly answer the question.
    - Use simple language a non-expert would understand immediately.
    - Keep it simple, but include important conditions if they affect correctness.
    - If the document content is insufficient to answer, write exactly:
      "The documents I have access to don't cover this. Try rephrasing the question please..."

    ## Additional Context
    _(Only include this section if the quick answer needs elaboration.)_
    Provide additional context, supporting clauses, exceptions, and related information drawn from the document.

    Structure this section with:
    - A short introductory sentence or two
    - Sub-headings (###) where there are distinct aspects (e.g., "### Exceptions", "### How it works")
    - Bullet points for lists of conditions, steps, or rules
    - Keep each bullet to one clear idea

    ## Follow-Up Questions
    List 2–3 short questions the user is likely to ask next, based on the document content and their original question.
    - Each question must use actual terms, names, or conditions from the document — never placeholder text like [term] or [condition].
    - Each question must be answerable from the provided document excerpts.
    - Format as a numbered list."""
    )


def summarize_elements(query: str, elements: List[Dict[str, Any]]) -> Optional[str]:
    """Return an LLM-generated summary of the matched elements, or None if there's nothing to summarize."""
    if not elements:
        return None

    prompt = _build_prompt(query, elements)
    return get_llm_response(prompt)