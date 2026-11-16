"""
MCP server routes (a port of the Landing Page's api/mcp.js transport) plus the token management the website uses.

  POST /mcp                      MCP, Streamable HTTP, stateless, JSON replies. Bearer token.
  GET  /mcp                      405 (nothing to stream), as in the reference
  GET  /mcp/audio/{file}         download an MP3 through a signed, expiring link (no login)
  GET  /api/mcp/info             what the "Connect Grok" page shows: server URL, tools
  GET/POST/DELETE /api/mcp/tokens   create / list / revoke the signed-in user's tokens

CORS for /mcp is open (the bearer token is the only credential; no cookie is ever read), see
McpOpenCorsMiddleware and the reasoning in the reference implementation.
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

import mcp_server
import mcp_tokens
import tts_service
from auth import get_current_user
from database import SessionLocal, get_db
from models import User

logger = logging.getLogger("mcp_routes")
router = APIRouter(tags=["mcp"])

CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Mcp-Protocol-Version, Mcp-Session-Id, Last-Event-ID",
  "Access-Control-Expose-Headers": "WWW-Authenticate, Mcp-Session-Id",
  "Access-Control-Max-Age": "86400",
}


class McpOpenCorsMiddleware(BaseHTTPMiddleware):
  """Open CORS for /mcp only (the site's own routes keep the frontend-origin allow-list)."""

  async def dispatch(self, request: Request, call_next):
    path = request.url.path
    if path == "/mcp" or path == "/mcp/":
      if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS)
      response = await call_next(request)
      for k, v in CORS.items():
        response.headers[k] = v
      return response
    return await call_next(request)


def public_base_url(request: Request) -> str:
  """The address people reach this server on: PUBLIC_BASE_URL, else the proxy headers, else the request."""
  configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
  if configured:
    return configured
  proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
  host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.headers.get("host", "")
  if proto and host:
    return f"{proto}://{host}"
  return str(request.base_url).rstrip("/")


def _json(status: int, body, headers: dict | None = None) -> JSONResponse:
  return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store", **(headers or {})})


# ------------------------------- the MCP endpoint -------------------------------

async def _mcp_post(request: Request, db: Session):
  auth = request.headers.get("authorization", "")
  raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
  found = mcp_tokens.find_token(db, raw)
  if not found:
    # Unknown, revoked, or its owner was removed: the same answer.
    return _json(401, mcp_server.rpc_error(None, -32001, "Missing or invalid token"),
                 {"WWW-Authenticate": 'Bearer realm="tcf-text-to-speech"'})
  token, user = found

  if mcp_server.rate_limited(token.id):
    return _json(429, mcp_server.rpc_error(None, -32000, f"Too many requests: max {mcp_server.RATE_PER_MIN} per minute"), {"Retry-After": "30"})

  declared = request.headers.get("content-length")
  if declared and declared.isdigit() and int(declared) > mcp_server.MAX_BODY:
    return _json(413, mcp_server.rpc_error(None, -32700, "Request too large"))
  body = await request.body()
  if len(body) > mcp_server.MAX_BODY:
    return _json(413, mcp_server.rpc_error(None, -32700, "Request too large"))
  try:
    parsed = json.loads(body.decode("utf-8"))
  except Exception:
    return _json(400, mcp_server.rpc_error(None, -32700, "Parse error"))

  mcp_tokens.touch(db, token)
  ctx = mcp_server.McpContext(
    user_id=user.id, email=user.email, token_id=token.id, token_name=token.name,
    base_url=public_base_url(request), session_factory=SessionLocal,
  )

  if isinstance(parsed, list):
    if not parsed:
      return _json(400, mcp_server.rpc_error(None, -32600, "Empty batch"))
    out = [r for r in [await mcp_server.handle_message(m, ctx) for m in parsed[:20]] if r is not None]
    return _json(200, out) if out else Response(status_code=202)
  out = await mcp_server.handle_message(parsed, ctx)
  return _json(200, out) if out is not None else Response(status_code=202)


@router.post("/mcp")
async def mcp_post(request: Request, db: Session = Depends(get_db)):
  return await _mcp_post(request, db)


@router.post("/mcp/", include_in_schema=False)
async def mcp_post_slash(request: Request, db: Session = Depends(get_db)):
  return await _mcp_post(request, db)


def _mcp_get():
  # Stateless server, nothing to push: the optional GET stream is answered 405 as the spec allows.
  return _json(405, mcp_server.rpc_error(None, -32000, "This MCP server is stateless; use POST."), {"Allow": "POST"})


@router.get("/mcp")
async def mcp_get():
  return _mcp_get()


@router.get("/mcp/", include_in_schema=False)
async def mcp_get_slash():
  return _mcp_get()


@router.get("/mcp/audio/{file_name}")
async def mcp_audio(file_name: str, exp: str = "", sig: str = ""):
  """Download an MP3 through the signed link a tool returned. The signature is bound to the file and its expiry."""
  if not mcp_server.verify_download(file_name, exp, sig):
    raise HTTPException(status_code=403, detail="This link is invalid or has expired.")
  path = os.path.join(tts_service.AUDIO_STORAGE_PATH, file_name)
  if not os.path.isfile(path):
    raise HTTPException(status_code=404, detail="This file is no longer available (audio is stored temporarily).")
  media = "audio/mpeg" if file_name.endswith(".mp3") else "audio/wav"
  return FileResponse(path, media_type=media, filename=file_name, headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------- token management (website) -------------------------------

class CreateTokenRequest(BaseModel):
  name: str = Field(default="Grok", max_length=80)


@router.get("/api/mcp/info")
async def mcp_info(request: Request, _user: User = Depends(get_current_user)) -> dict:
  base = public_base_url(request)
  return {
    "mcp_url": f"{base}/mcp",
    "transport": "streamable-http (stateless, JSON)",
    "languages": tts_service.list_languages(),
    "tools": [{"name": t["name"], "title": t["title"], "description": t["description"]} for t in mcp_server.TOOLS],
    "max_active_tokens": mcp_tokens.MAX_ACTIVE_PER_USER,
  }


@router.get("/api/mcp/tokens")
async def list_tokens(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
  return {"tokens": mcp_tokens.list_tokens(db, user)}


@router.post("/api/mcp/tokens", status_code=201)
async def create_token(payload: CreateTokenRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
  """Create a token. It is returned here ONCE; only its hash is kept."""
  try:
    raw, view = mcp_tokens.create_token(db, user, payload.name)
  except mcp_tokens.TooManyTokens:
    raise HTTPException(status_code=409, detail=f"You already have {mcp_tokens.MAX_ACTIVE_PER_USER} active tokens. Revoke one first.")
  return {"token": raw, "record": view}


@router.delete("/api/mcp/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
  if not mcp_tokens.revoke_token(db, user, token_id):
    raise HTTPException(status_code=404, detail="Token not found.")
  return Response(status_code=204)
