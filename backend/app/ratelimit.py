"""slowapi limiter keyed on the real client IP (first X-Forwarded-For hop)."""

from slowapi import Limiter
from starlette.requests import Request

from app.config import get_settings


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip, enabled=get_settings().APP_ENV != "test")
