"""Deterministic offline provider used by tests and for running without any API key.

Embeddings are hashed bag-of-words vectors (so similar text -> similar vectors).
Chat returns a scripted response if one is queued, otherwise "{}" for JSON requests
(triggering heuristic fallbacks) and an extractive, cited answer for normal requests.
"""

import hashlib
import math
import re
from collections.abc import AsyncIterator

from app.llm.base import ChatMessage

_TOKEN = re.compile(r"[a-z0-9]+")


def hashed_embedding(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeProvider:
    name = "fake"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.chat_calls: list[tuple[str, list[ChatMessage]]] = []
        self.scripted: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [hashed_embedding(t, self.dim) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return hashed_embedding(text, self.dim)

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [hashed_embedding(t, self.dim) for t in texts]

    def _answer(self, system: str) -> str:
        if self.scripted:
            return self.scripted.pop(0)
        # Extractive fallback: quote the first line of each source, cited.
        sources = re.findall(r"^\[(\d+)\] \(([^)]*)\)\n(.+)$", system, flags=re.MULTILINE)
        if not sources:
            return "The uploaded brochures don't specify this."
        lines = ["Here is what the uploaded brochures say:", ""]
        for n, _label, body in sources[:6]:
            lines.append(f"- {body.strip()[:160]} [{n}]")
        return "\n".join(lines)

    async def chat(
        self, system: str, messages: list[ChatMessage], *, json_mode: bool = False, temperature: float = 0.2
    ) -> str:
        self.chat_calls.append((system, messages))
        if json_mode and not self.scripted:
            return "{}"
        return self._answer(system)

    async def chat_stream(
        self, system: str, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        self.chat_calls.append((system, messages))
        text = self._answer(system)
        for i in range(0, len(text), 24):
            yield text[i : i + 24]

    async def transcribe_image(self, png_bytes: bytes, prompt: str) -> str:
        return ""
