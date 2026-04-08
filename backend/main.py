import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

load_dotenv()

app = FastAPI(title="TCF Canada API", version="0.1.0")

AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

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

app.include_router(dictionary_router)
app.include_router(passage_router)
app.include_router(performance_router)
app.include_router(auth_router)
app.include_router(learn_router)
app.include_router(tcf_exam_router)
app.include_router(tcf_listening_router)
app.include_router(tcf_writing_router)
app.include_router(tcf_speaking_router)


@app.on_event("startup")
async def on_startup() -> None:
  init_db()


@app.get("/")
async def root() -> dict[str, str]:
  return {"status": "ok", "service": "tcf-backend"}




