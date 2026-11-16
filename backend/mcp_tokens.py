"""
mcp_tokens.py — tokens for the MCP server (/mcp), a port of the Landing Page's api/_mcp_tokens.js.

A signed-in user creates a token on the "Connect Grok" page and pastes it into Grok. Grok then calls /mcp with
`Authorization: Bearer <token>`.

Rules (same as the reference implementation):
  - The token is shown ONCE, at creation. Only its SHA-256 is stored, so a copy of the database is not a copy of
    anyone's access.
  - A token acts AS the user who created it: the audio it generates is saved in that user's Audio History.
  - Revoking is immediate: every call looks the token up again.
  - Comparison is timing-safe.
"""

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import McpToken, User

PREFIX = "tcfmcp_"
MAX_ACTIVE_PER_USER = 10
LAST_USED_RESOLUTION_S = 60  # "last used" is useful; a database write on every call is not


def _sha(value: str) -> str:
  return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_view(t: McpToken) -> dict:
  """The public view: never the hash."""
  return {
    "id": t.id,
    "name": t.name,
    "hint": t.hint,
    "created_at": t.created_at.isoformat() if t.created_at else None,
    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
    "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
  }


class TooManyTokens(Exception):
  pass


def create_token(db: Session, user: User, name: str | None) -> tuple[str, dict]:
  """Returns (raw_token, view). The raw token exists only in this return value."""
  active = db.query(McpToken).filter(McpToken.user_id == user.id, McpToken.revoked_at.is_(None)).count()
  if active >= MAX_ACTIVE_PER_USER:
    raise TooManyTokens()
  token = PREFIX + secrets.token_urlsafe(32)
  row = McpToken(
    id=secrets.token_hex(8),
    user_id=user.id,
    name=(name or "").strip()[:80] or "Grok",
    hint=token[: len(PREFIX) + 4] + "…" + token[-4:],
    token_hash=_sha(token),
  )
  db.add(row)
  db.commit()
  db.refresh(row)
  return token, token_view(row)


def list_tokens(db: Session, user: User) -> list[dict]:
  rows = db.query(McpToken).filter(McpToken.user_id == user.id).order_by(McpToken.created_at.desc()).all()
  return [token_view(r) for r in rows]


def revoke_token(db: Session, user: User, token_id: str) -> bool:
  """Revoke one of the user's own tokens. False if there is no such token for this user."""
  row = db.query(McpToken).filter(McpToken.id == token_id, McpToken.user_id == user.id).first()
  if not row:
    return False
  if not row.revoked_at:
    row.revoked_at = datetime.utcnow()
    db.commit()
  return True


def find_token(db: Session, raw: str) -> Optional[tuple[McpToken, User]]:
  """The active token and its owner for a presented token, or None. Timing-safe."""
  if not isinstance(raw, str) or not raw.startswith(PREFIX) or len(raw) > 200:
    return None
  row = db.query(McpToken).filter(McpToken.token_hash == _sha(raw)).first()
  if not row or row.revoked_at:
    return None
  if not hmac.compare_digest(row.token_hash, _sha(raw)):
    return None
  user = db.query(User).filter(User.id == row.user_id).first()
  if not user:
    return None  # the owner was removed: the token stops working
  return row, user


def touch(db: Session, row: McpToken) -> None:
  now = datetime.utcnow()
  if row.last_used_at and (now - row.last_used_at).total_seconds() < LAST_USED_RESOLUTION_S:
    return
  try:
    row.last_used_at = now
    db.commit()
  except Exception:
    db.rollback()  # not worth failing a call
