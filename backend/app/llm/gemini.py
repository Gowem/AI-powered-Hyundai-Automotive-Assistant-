"""Google Gemini provider (google-genai SDK)."""

import asyncio
import logging
import math
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.config import Settings
from app.llm.base import ChatMessage, LLMError
from app.llm.retry import retrying

EMBED_BATCH = 50
# Chat calls retry only transient server errors; quota (429) / missing model (404) switch model at once.
CHAT_RETRY_CODES = frozenset({500, 502, 503, 504})
FALLBACK_ROUNDS = 2  # if every model is busy, pause and walk the chain once more
ROUND_PAUSE_SECONDS = 8.0
logger = logging.getLogger("app.llm")


def _normalise(vec: list[float]) -> list[float]:
    # gemini-embedding-001 vectors truncated below 3072 dims are not unit-normalised.
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is not set")
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=settings.LLM_TIMEOUT_SECONDS * 1000),
        )
        self.chat_model = settings.GEMINI_CHAT_MODEL
        self.planner_model = settings.GEMINI_PLANNER_MODEL or settings.GEMINI_CHAT_MODEL
        self.fallback_models = [m.strip() for m in settings.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]
        self.embed_model = settings.GEMINI_EMBED_MODEL
        self.dim = settings.EMBEDDING_DIM
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    async def available_chat_models(self) -> list[str]:
        """Names of models that support generateContent (logged at startup to validate config)."""
        names: list[str] = []
        pager = await self.client.aio.models.list(config={"page_size": 200})
        async for m in pager:
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions and m.name:
                names.append(m.name.removeprefix("models/"))
        return names

    async def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            async for attempt in retrying(5):
                with attempt:
                    resp = await self.client.aio.models.embed_content(
                        model=self.embed_model,
                        contents=batch,  # type: ignore[arg-type]
                        config=types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim),
                    )
            embs = resp.embeddings or []
            if len(embs) != len(batch):
                raise LLMError("Embedding count mismatch from Gemini")
            for e in embs:
                values = list(e.values or [])
                if len(values) != self.dim:
                    raise LLMError(f"Embedding dimension {len(values)} != {self.dim}")
                out.append(_normalise(values))
        return out

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_QUERY")

    @staticmethod
    def _contents(messages: list[ChatMessage]) -> list[types.Content]:
        return [
            types.Content(role="user" if m.role == "user" else "model", parts=[types.Part(text=m.content)])
            for m in messages
        ]

    def _models(self, primary: str | None = None) -> list[str]:
        return list(dict.fromkeys([primary or self.chat_model, self.chat_model, *self.fallback_models]))

    @staticmethod
    def _should_fall_back(exc: BaseException) -> bool:
        """Overloaded / rate-limited / unknown model: try the next model instead of failing."""
        code = getattr(exc, "code", None)
        return isinstance(exc, asyncio.TimeoutError) or code in (404, 429, 500, 503, 504)

    async def _generate(
        self, contents: object, config: types.GenerateContentConfig, limit: float, primary: str | None = None
    ) -> str:
        last: BaseException | None = None
        for round_no in range(FALLBACK_ROUNDS):
            if round_no:
                await asyncio.sleep(ROUND_PAUSE_SECONDS)  # every model busy/rate-limited: wait, try the chain again
            for model in self._models(primary):
                try:
                    return await self._generate_once(model, contents, config, limit)
                except Exception as exc:
                    if not self._should_fall_back(exc):
                        raise
                    logger.warning(
                        "Gemini model %s unavailable (%s)", model, getattr(exc, "code", exc.__class__.__name__)
                    )
                    last = exc
        assert last is not None
        raise last

    async def _generate_once(
        self, model: str, contents: object, config: types.GenerateContentConfig, limit: float
    ) -> str:
        async for attempt in retrying(2, CHAT_RETRY_CODES):
            with attempt:
                resp = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model,
                        contents=contents,  # type: ignore[arg-type]
                        config=config,
                    ),
                    timeout=limit,
                )
        return resp.text or ""

    async def chat(
        self, system: str, messages: list[ChatMessage], *, json_mode: bool = False, temperature: float = 0.2
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
        )
        # Structured query planning is a small task: run it on the planner (lite) model, which has its own quota.
        primary = self.planner_model if json_mode else None
        return await self._generate(self._contents(messages), config, self.timeout, primary)

    async def chat_stream(
        self, system: str, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        last: BaseException | None = None
        for round_no in range(FALLBACK_ROUNDS):
            if round_no:
                await asyncio.sleep(ROUND_PAUSE_SECONDS)
            for model in self._models():
                started = False
                try:
                    async for attempt in retrying(2, CHAT_RETRY_CODES):
                        with attempt:
                            stream = await asyncio.wait_for(
                                self.client.aio.models.generate_content_stream(
                                    model=model, contents=self._contents(messages), config=config
                                ),
                                timeout=self.timeout,
                            )
                            iterator = stream.__aiter__()
                            first = await asyncio.wait_for(iterator.__anext__(), timeout=self.timeout)
                    started = True
                    if first.text:
                        yield first.text
                    async for chunk in iterator:
                        if chunk.text:
                            yield chunk.text
                    return
                except StopAsyncIteration:
                    return
                except Exception as exc:
                    if started or not self._should_fall_back(exc):
                        raise
                    logger.warning(
                        "Gemini model %s unavailable (%s)", model, getattr(exc, "code", exc.__class__.__name__)
                    )
                    last = exc
        assert last is not None
        raise last

    async def transcribe_image(self, png_bytes: bytes, prompt: str) -> str:
        return await self._generate(
            [types.Part.from_bytes(data=png_bytes, mime_type="image/png"), prompt],
            types.GenerateContentConfig(temperature=0.0),
            self.timeout * 2,
        )
