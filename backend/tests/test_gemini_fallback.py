import pytest

from app.config import get_settings
from app.llm.gemini import GeminiProvider


class _Err(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"error {code}")
        self.code = code


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _Models:
    def __init__(self, failing: set[str], code: int = 503) -> None:
        self.failing, self.code, self.calls = failing, code, []

    async def generate_content(self, model, contents, config):  # type: ignore[no-untyped-def]
        self.calls.append(model)
        if model in self.failing:
            raise _Err(self.code)
        return _Resp(f"answer from {model}")

    async def generate_content_stream(self, model, contents, config):  # type: ignore[no-untyped-def]
        self.calls.append(model)
        failing, code = model in self.failing, self.code

        async def gen():  # type: ignore[no-untyped-def]
            if failing:
                raise _Err(code)
            for t in ("a", "b"):
                yield _Resp(f"{model}:{t} ")

        return gen()


def _provider(models: _Models) -> GeminiProvider:
    s = get_settings().model_copy(
        update={"GEMINI_API_KEY": "x", "GEMINI_CHAT_MODEL": "primary", "GEMINI_FALLBACK_MODELS": "second,third"}
    )
    p = GeminiProvider(s)
    p.client = type("C", (), {"aio": type("A", (), {"models": models})()})()  # type: ignore[assignment]
    return p


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):  # type: ignore[no-untyped-def]
    from tenacity import AsyncRetrying, stop_after_attempt

    import app.llm.gemini as g

    monkeypatch.setattr(g, "retrying", lambda n, codes=None: AsyncRetrying(stop=stop_after_attempt(1), reraise=True))


async def test_chat_falls_back_when_model_overloaded() -> None:
    models = _Models({"primary"})
    assert await _provider(models).chat("sys", []) == "answer from second"
    assert models.calls == ["primary", "second"]


async def test_stream_falls_back_before_first_token() -> None:
    models = _Models({"primary", "second"})
    out = [t async for t in _provider(models).chat_stream("sys", [])]
    assert "".join(out) == "third:a third:b "


async def test_non_retryable_error_is_raised() -> None:
    models = _Models({"primary"}, code=400)
    with pytest.raises(_Err):
        await _provider(models).chat("sys", [])
    assert models.calls == ["primary"]


def test_asyncio_timeout_falls_back() -> None:
    assert GeminiProvider._should_fall_back(TimeoutError())
