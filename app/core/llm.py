"""Provider-agnostic LLM configuration and client.

Reads LLM_PROVIDER from the environment and talks to whichever provider
was selected at setup time (see infra-tdb-platform's scripts/bootstrap.sh).

LiteLLM is the integration point, not a hand-rolled per-provider client:
it owns the actual protocol work per provider (request shape, auth
headers, response parsing, retries) so we never hand-write a
provider-specific client. What LiteLLM does NOT do for us is decide which
provider/model/credential a given deployment should use - that's
inherently routing configuration, not integration logic, and every
LiteLLM consumer needs some form of it (LiteLLM's own proxy config.yaml
has the identical shape: a table mapping model name -> {model, api_key,
api_base}).

PROVIDERS below is exactly that table, and it's the ONLY thing that grows
when a new provider is added - _resolve_call_kwargs() itself never
changes. Adding a new cloud provider that authenticates with a single
bearer-style API key (most of them: OpenAI, Grok, Anthropic, Cohere,
Groq, Mistral, DeepSeek...) means adding one row here, nothing else.

Grok and Ollama are both reached through LiteLLM's OpenAI-compatible
routing (Grok via the "xai/" prefix, Ollama via the generic "openai/"
prefix + api_base, since Ollama's OpenAI-compatible endpoint is what
OLLAMA_BASE_URL already points at) - only OpenAI needs no prefix at all.
"""

import os
import litellm

from talkingdb.logger.console import logger

# --------------------------------------------------------------- providers
# One row per provider.
#
#   model  : the model ID passed to the provider itself (fixed per
#            provider, not user-configurable - decided at setup time).
#   prefix : LiteLLM's own routing prefix for this provider (see
#            docs.litellm.ai/docs/providers). "" for OpenAI, which is
#            LiteLLM's implicit default and needs no prefix.
#   local  : True if this provider runs locally and is configured via
#            <PROVIDER>_BASE_URL instead of <PROVIDER>_API_KEY.
PROVIDERS = {
    "openai": {"model": "gpt-5.4-mini", "prefix": "", "local": False},
    "grok": {"model": "grok-4.3", "prefix": "xai/", "local": False},
    "ollama": {"model": "qwen3:4b", "prefix": "openai/", "local": True},
}

DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434/v1"

# Ollama doesn't check the API key, but LiteLLM's OpenAI-compatible path
# may still expect a non-empty string depending on version/config.
_LOCAL_PLACEHOLDER_API_KEY = "not-needed"


class LLMNotConfiguredError(Exception):
    """Raised when LLM_PROVIDER is missing/unknown or a required secret is absent."""


def _resolve_call_kwargs(provider: str) -> dict:
    """Build the litellm.completion() kwargs (model/api_key/api_base) for a provider.

    Table-driven, not branched: every provider in PROVIDERS is handled by
    the same two code paths (local vs. cloud) below. Adding a new cloud
    provider that takes a single API key never touches this function.
    """
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise LLMNotConfiguredError(
            f"Unknown LLM_PROVIDER: {provider!r}. Supported: {sorted(PROVIDERS)}"
        )

    model = f"{cfg['prefix']}{cfg['model']}"

    if cfg["local"]:
        base_url = os.getenv(f"{provider.upper()}_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        return {"model": model, "api_key": _LOCAL_PLACEHOLDER_API_KEY, "api_base": base_url}

    key_name = f"{provider.upper()}_API_KEY"
    api_key = os.getenv(key_name)
    if not api_key:
        raise LLMNotConfiguredError(f"{key_name} is not set")
    return {"model": model, "api_key": api_key}


def is_configured() -> bool:
    """Whether LLM_PROVIDER and its required secret/URL are set. Used at startup."""
    provider = os.getenv("LLM_PROVIDER")
    if not provider:
        return False
    try:
        _resolve_call_kwargs(provider)
        return True
    except LLMNotConfiguredError:
        return False


def get_llm_response(prompt: str) -> str:
    """Send a prompt to the configured provider and return the text response."""
    provider = os.getenv("LLM_PROVIDER")
    if not provider:
        raise LLMNotConfiguredError("LLM_PROVIDER is not set")

    kwargs = _resolve_call_kwargs(provider)

    if PROVIDERS[provider]["local"]:
        prompt = f"{prompt} /no_think"

    completion = litellm.completion(
        messages=[{"role": "user", "content": prompt}],
        timeout=300,
        **kwargs
    )
    return completion.choices[0].message.content