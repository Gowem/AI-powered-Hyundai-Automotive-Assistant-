"""OpenAI provider (alternative to Gemini)."""

import base64
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import ChatMessage, LLMError
from app.llm.retry import retrying

EMBED_BATCH = 100


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is not set")
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=0)
        self.chat_model = settings.OPENAI_CHAT_MODEL
        self.embed_model = settings.OPENAI_EMBED_MODEL
        self.dim = settings.EMBEDDING_DIM

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            async for attempt in retrying(5):
                with attempt:
                    resp = await self.client.embeddings.create(model=self.embed_model, input=batch, dimensions=self.dim)
            out.extend([list(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)])
        return out

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    @staticmethod
    def _msgs(system: str, messages: list[ChatMessage]) -> list[Any]:
        return [{"role": "system", "content": system}, *({"role": m.role, "content": m.content} for m in messages)]

    async def chat(
        self, system: str, messages: list[ChatMessage], *, json_mode: bool = False, temperature: float = 0.2
    ) -> str:
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        async for attempt in retrying(3):
            with attempt:
                resp = await self.client.chat.completions.create(
                    model=self.chat_model, messages=self._msgs(system, messages), temperature=temperature, **kwargs
                )
        return resp.choices[0].message.content or ""

    async def chat_stream(
        self, system: str, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        stream = None
        async for attempt in retrying(3):
            with attempt:
                stream = await self.client.chat.completions.create(
                    model=self.chat_model, messages=self._msgs(system, messages), temperature=temperature, stream=True
                )
        assert stream is not None
        async for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content

    async def transcribe_image(self, png_bytes: bytes, prompt: str) -> str:
        b64 = base64.b64encode(png_bytes).decode()
        async for attempt in retrying(3):
            with attempt:
                resp = await self.client.chat.completions.create(
                    model=self.chat_model,
                    temperature=0,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            ],
                        }
                    ],
                )
        if not resp.choices:
            raise LLMError("Empty OCR response")
        return resp.choices[0].message.content or ""
