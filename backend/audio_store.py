"""Durable audio files.

Render's disk is wiped on every restart and is not shared between instances, so a URL that only
points at a local file 404s. Bytes are stored in Postgres (and cached on the local disk). The
serving route reads the database when the file is gone, and a listening question never returns a
URL whose bytes are not stored.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database import Base, SessionLocal, engine

logger = logging.getLogger("tcf.audio")

_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
_ready = False


def _dir() -> str:
    from tcf_ai_service import AUDIO_STORAGE_PATH
    os.makedirs(AUDIO_STORAGE_PATH, exist_ok=True)
    return AUDIO_STORAGE_PATH


def safe_name(url_or_name: str) -> str | None:
    name = os.path.basename((url_or_name or "").split("?", 1)[0].strip())
    if not name or not _NAME.match(name) or name in (".", ".."):
        return None
    return name


def ensure_schema() -> None:
    global _ready
    if _ready:
        return
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ready = True


def _path(name: str) -> str:
    return os.path.join(_dir(), name)


def stored_script_key(script_key: str | None) -> str | None:
    """A cache key that always fits VARCHAR(64). Longer keys are their sha256 hex digest."""
    if not script_key:
        return None
    if len(script_key) <= 64:
        return script_key
    return hashlib.sha256(script_key.encode("utf-8")).hexdigest()


def save(name: str, data: bytes, mime: str = "audio/mpeg", script_key: str | None = None) -> str:
    """Write `data` to the local cache and the database. Returns `/audio/<name>`.

    A database error is logged and does not fail the request: the file is already on disk,
    and the player can still be given the URL.
    """
    clean = safe_name(name)
    if clean is None or not data:
        raise ValueError("Invalid audio name or empty audio.")
    ensure_schema()
    key = stored_script_key(script_key)
    path = _path(clean)
    with open(path, "wb") as handle:
        handle.write(data)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO stored_audio (name, script_key, mime, content, created_at) "
                "VALUES (:name, :key, :mime, :content, :now)"
            ),
            {"name": clean, "key": key, "mime": mime, "content": data, "now": datetime.utcnow()},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        try:
            db.execute(
                text(
                    "UPDATE stored_audio SET content = :content, mime = :mime, script_key = COALESCE(:key, script_key) "
                    "WHERE name = :name"
                ),
                {"name": clean, "key": key, "mime": mime, "content": data},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not update cached audio %s; the file is still being returned.", clean)
    except Exception:
        db.rollback()
        logger.exception("Could not store audio %s in the database; the file is still being returned.", clean)
    finally:
        db.close()
    return f"/audio/{clean}"


def available(url_or_name: str | None) -> bool:
    name = safe_name(url_or_name or "")
    if name is None:
        return False
    if os.path.isfile(_path(name)) and os.path.getsize(_path(name)) > 0:
        return True
    ensure_schema()
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT 1 FROM stored_audio WHERE name = :name"), {"name": name}).first()
        return row is not None
    finally:
        db.close()


def load(url_or_name: str) -> tuple[bytes, str] | None:
    """Bytes and mime. Restores the local file from the database when the disk copy is gone."""
    name = safe_name(url_or_name)
    if name is None:
        return None
    path = _path(name)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as handle:
            data = handle.read()
        return data, _mime_for(name)
    ensure_schema()
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT content, mime FROM stored_audio WHERE name = :name"),
            {"name": name},
        ).first()
    finally:
        db.close()
    if row is None or not row[0]:
        return None
    data = bytes(row[0])
    mime = row[1] or _mime_for(name)
    try:
        with open(path, "wb") as handle:
            handle.write(data)
    except OSError as error:
        logger.warning("Could not restore %s to disk: %s", name, error)
    return data, mime


def find_by_script(script_key: str) -> str | None:
    script_key = stored_script_key(script_key)
    if not script_key:
        return None
    ensure_schema()
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT name FROM stored_audio WHERE script_key = :key ORDER BY created_at DESC LIMIT 1"),
            {"key": script_key},
        ).first()
    finally:
        db.close()
    if row is None:
        return None
    return f"/audio/{row[0]}"


def _mime_for(name: str) -> str:
    return "audio/wav" if name.endswith(".wav") else "audio/mpeg"
