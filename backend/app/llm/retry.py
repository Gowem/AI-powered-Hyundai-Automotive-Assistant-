"""Shared retry policy: retry on rate limits, 5xx and timeouts with exponential backoff."""

import asyncio
import logging

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger("app.llm")

RETRYABLE_CODES = {408, 409, 429, 500, 502, 503, 504}


def _status_of(exc: BaseException) -> int | None:
    for attr in ("code", "status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(exc, "response", None)
    code = getattr(resp, "status_code", None)
    return code if isinstance(code, int) else None


def is_retryable(exc: BaseException, codes: frozenset[int] | set[int] = RETRYABLE_CODES) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException, httpx.NetworkError, ConnectionError)):
        return True
    code = _status_of(exc)
    return code in codes


def retrying(attempts: int = 3, codes: frozenset[int] | set[int] = RETRYABLE_CODES) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=2, max=30),
        retry=retry_if_exception(lambda e: is_retryable(e, codes)),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
