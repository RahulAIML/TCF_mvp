"""Guests are served through one shared demo account; nothing personal should accumulate on it."""
from __future__ import annotations

DEMO_EMAIL = "demo@tcf.local"


def is_guest(user: object) -> bool:
    return user is None or getattr(user, "email", None) == DEMO_EMAIL
