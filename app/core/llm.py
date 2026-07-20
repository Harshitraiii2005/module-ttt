"""Provider-agnostic LLM configuration and client.

Reads LLM_PROVIDER from the environment and talks to whichever provider
was selected at setup time (see infra-tdb-platform's configure_llm_provider.sh).

OpenAI, Grok, and Ollama all speak the same "OpenAI-compatible" chat
completions API, so a single client class covers all three - only the
base_url, api_key, and model differ per provider.
"""

import os

from openai import OpenAI

# --------------------------------------------------------------- providers
# Model IDs are fixed per provider (not user-configurable), matching what
# was decided during setup. Only the API key (cloud) or base URL (local)
# comes from the environment.
PROVIDER_MODELS = {
    "openai": "gpt-5.4-mini",
    "grok": "grok-4.3",
    "ollama": "qwen3:4b",
}

# Grok's OpenAI-compatible endpoint. OpenAI needs no base_url override -
# the SDK already points at OpenAI by default.
GROK_BASE_URL = "https://api.x.ai/v1"

# Default local Ollama address. Only overridden if the user set
# OLLAMA_BASE_URL explicitly (e.g. Ollama running on a different host/port).
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class LLMNotConfiguredError(Exception):
    """Raised when LLM_PROVIDER is missing/unknown or a required secret is absent."""


def _build_client(provider: str) -> OpenAI:
    """Create an OpenAI-compatible client for the given provider."""
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMNotConfiguredError("OPENAI_API_KEY is not set")
        return OpenAI(api_key=api_key)

    if provider == "grok":
        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            raise LLMNotConfiguredError("GROK_API_KEY is not set")
        return OpenAI(api_key=api_key, base_url=GROK_BASE_URL)

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        # Ollama doesn't check the key, but the SDK requires a non-empty string.
        return OpenAI(api_key="ollama", base_url=base_url)

    raise LLMNotConfiguredError(f"Unknown LLM_PROVIDER: {provider!r}")


def get_llm_response(prompt: str) -> str:
    """Send a prompt to the configured provider and return the text response."""
    provider = os.getenv("LLM_PROVIDER")
    if not provider:
        raise LLMNotConfiguredError("LLM_PROVIDER is not set")

    client = _build_client(provider)
    model = PROVIDER_MODELS[provider]

    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content