import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import Response

import pregen_pool
from database import init_db
from routers.auth_routes import router as auth_router
from routers.dictionary import router as dictionary_router
from routers.passage_routes import router as passage_router
from routers.performance_routes import router as performance_router
from routers.learn_routes import router as learn_router
from routers.tcf_exam_routes import router as tcf_exam_router
from routers.tcf_listening_routes import router as tcf_listening_router
from routers.tcf_speaking_routes import router as tcf_speaking_router
from routers.tcf_writing_routes import router as tcf_writing_router
from routers.pronunciation_routes import router as pronunciation_router
from routers.ai_chat_routes import router as ai_chat_router
from routers.tts_routes import router as tts_router
from learner import LearnerMiddleware
from routers.mcp_routes import McpOpenCorsMiddleware, router as mcp_router

load_dotenv()

app = FastAPI(title="TCF Canada API", version="0.1.0")

AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/audio/{file_name}")
def serve_audio(file_name: str) -> Response:
  """Serve a stored recording. If this instance's disk lost the file, the database copy is used."""
  import audio_store
  loaded = audio_store.load(file_name)
  if loaded is None:
    raise HTTPException(status_code=404, detail="This audio is no longer on the server. Please generate it again.")
  data, mime = loaded
  return Response(content=data, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})

configured_origins = [
  origin.strip()
  for origin in os.getenv(
    "FRONTEND_ORIGIN",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000"
  ).split(",")
  if origin.strip()
]
frontend_origins = sorted(
  set(configured_origins).union({
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000"
  })
)
app.add_middleware(
  CORSMiddleware,
  allow_origins=frontend_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"]
)
# Added after CORSMiddleware, so it runs first: /mcp is open to any origin (bearer token only, no cookies).
app.add_middleware(McpOpenCorsMiddleware)
app.add_middleware(LearnerMiddleware)

app.include_router(dictionary_router)
app.include_router(passage_router)
app.include_router(performance_router)
app.include_router(auth_router)
app.include_router(learn_router)
app.include_router(tcf_exam_router)
app.include_router(tcf_listening_router)
app.include_router(tcf_writing_router)
app.include_router(tcf_speaking_router)
app.include_router(pronunciation_router)
app.include_router(ai_chat_router)
app.include_router(tts_router)
app.include_router(mcp_router)


def _warm_in_background() -> None:
  """Fill pools after the process is already accepting health checks, so warmup cannot fail the deploy."""
  time.sleep(float(os.getenv("PREGEN_WARM_DELAY_SECONDS", "3")))
  try:
    pregen_pool.warm_all()
  except Exception:
    import logging
    logging.getLogger("tcf").exception("Background pool warm-up failed")


@app.on_event("startup")
async def on_startup() -> None:
  # init_db talks to Postgres. Do it off the event loop so the process can answer health checks.
  import anyio
  await anyio.to_thread.run_sync(init_db)
  # Do not generate questions on the startup thread. A burst of model and ffmpeg work at boot
  # has been restarting the instance (instant 502s from the proxy).
  threading.Thread(target=_warm_in_background, name="pregen-warm", daemon=True).start()


@app.get("/api/pregen/stats")
def pregen_stats() -> dict:
  return pregen_pool.all_stats()


def _deploy_commit() -> str:
  """Render sets RENDER_GIT_COMMIT. Local and other hosts fall back to dev."""
  return os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "dev"


@app.get("/")
async def root() -> dict[str, str]:
  return {"status": "ok", "service": "tcf-backend", "commit": _deploy_commit()}


@app.get("/api/version")
async def version() -> dict[str, str]:
  """No database and no provider. This must answer even when generation threads are all busy."""
  return {"service": "tcf-backend", "commit": _deploy_commit()}


@app.get("/api/health")
@app.get("/healthz")
async def health() -> dict[str, str]:
  """Liveness only. A provider call here can stall the only worker, so this handler never makes one."""
  return {"status": "ok", "service": "tcf-backend", "commit": _deploy_commit()}
