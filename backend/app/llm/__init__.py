"""Provider factory."""

from app.config import get_settings
from app.llm.base import LLMProvider

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.LLM_PROVIDER == "openai":
            from app.llm.openai import OpenAIProvider

            _provider = OpenAIProvider(settings)
        elif settings.LLM_PROVIDER == "fake":
            from app.llm.fake import FakeProvider

            _provider = FakeProvider(settings.EMBEDDING_DIM)
        else:
            from app.llm.gemini import GeminiProvider

            _provider = GeminiProvider(settings)
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Override the provider (used by tests)."""
    global _provider
    _provider = provider
