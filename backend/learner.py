"""Who a practice item was served to.

Signed-in learners are `user:<id>`. Guests are `guest:<learner-id>` from the X-Learner-Id header
or the tcf_learner_id cookie. The shared demo account is never used as an identity: two guests
must not share a seen-set. When neither a real user nor a device id is present, the caller's
session id is used so older clients still dedupe within one session.
"""
from __future__ import annotations

import contextvars
import os
import re
from contextlib import contextmanager

from starlette.requests import Request

from guest import DEMO_EMAIL

_LEARNER = contextvars.ContextVar("tcf_learner", default=None)
_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
HEADER = "x-learner-id"
COOKIE = "tcf_learner_id"


def normalize_learner_id(raw: str | None) -> str | None:
    if not raw:
        return None
    clean = raw.strip()
    return clean if _ID.match(clean) else None


def _user_id_from_authorization(header: str | None) -> int | None:
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from jose import jwt
        from auth import JWT_ALGORITHM, JWT_SECRET
        payload = jwt.decode(token, JWT_SECRET or os.getenv("JWT_SECRET", ""), algorithms=[JWT_ALGORITHM])
        email = str(payload.get("sub") or "")
    except Exception:
        return None
    if not email or email.lower() == DEMO_EMAIL:
        return None
    from database import SessionLocal
    from models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return int(user.id) if user is not None else None
    except Exception:
        return None
    finally:
        db.close()


def _cookie_value(request: Request) -> str | None:
    raw = request.headers.get("cookie") or ""
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE and value:
            return value
    return None


def resolve_request_learner(request: Request) -> str | None:
    """Stable key for this request, or None when the client sent nothing we can keep."""
    user_id = _user_id_from_authorization(request.headers.get("authorization"))
    if user_id is not None:
        return f"user:{user_id}"
    device = normalize_learner_id(request.headers.get(HEADER)) or normalize_learner_id(_cookie_value(request))
    if device:
        return f"guest:{device}"
    return None


def current_learner() -> str | None:
    """The request's learner key, or None outside a request (pool refill, scripts)."""
    return _LEARNER.get()


def active_learner(session_id: str | None = None) -> str:
    current = _LEARNER.get()
    if current:
        return current
    device = normalize_learner_id(session_id)
    if device:
        return f"guest:{device}"
    if session_id and session_id.strip():
        # Older clients send ids that are not uuid-shaped. Keep them, but don't mix guests together.
        slim = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64]
        if slim:
            return f"guest:{slim}"
    return "guest:anonymous"


@contextmanager
def push_learner(key: str | None):
    token = _LEARNER.set(key)
    try:
        yield key
    finally:
        _LEARNER.reset(token)


class LearnerMiddleware:
    """Bind the request's learner key for the duration of the call."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        key = resolve_request_learner(request)
        token = _LEARNER.set(key) if key else None
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                _LEARNER.reset(token)
