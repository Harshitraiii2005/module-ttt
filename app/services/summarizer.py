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
    print("###########################")
    print("THIS IS PROMPT BUILDING AREA")
    return (
        "You are summarizing search results from a document search system.\n"
        f'User query: "{query}"\n\n'
        "Matched excerpts:\n"
        f"{joined}\n\n"
        "Write a concise summary (3-5 sentences) of what these excerpts say "
        "in relation to the query. Only use information present in the excerpts."
    )


def summarize_elements(query: str, elements: List[Dict[str, Any]]) -> Optional[str]:
    """Return an LLM-generated summary of the matched elements, or None if there's nothing to summarize."""
    print("#####################")
    print(elements)
    if not elements:
        return None

    prompt = _build_prompt(query, elements)
    print("#########################")
    print(prompt)
    return get_llm_response(prompt)