"""Provider-agnostic LLM interface."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


class LLMError(Exception):
    """Raised for provider failures that should surface as a readable error."""


class LLMProvider(Protocol):
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed documents (RETRIEVAL_DOCUMENT task)."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (RETRIEVAL_QUERY task)."""
        ...

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed several search queries in one request."""
        ...

    async def chat(
        self, system: str, messages: list[ChatMessage], *, json_mode: bool = False, temperature: float = 0.2
    ) -> str: ...

    def chat_stream(
        self, system: str, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...

    async def transcribe_image(self, png_bytes: bytes, prompt: str) -> str: ...
