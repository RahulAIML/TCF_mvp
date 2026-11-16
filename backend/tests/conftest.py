"""Test setup: a throwaway SQLite database and audio folder, set BEFORE the app is imported."""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="tcf_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["AUDIO_STORAGE_PATH"] = os.path.join(_tmp, "audio")
os.environ["JWT_SECRET"] = "test-secret"
os.environ.pop("PUBLIC_BASE_URL", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ELEVENLABS_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app():
  from database import init_db
  import main
  init_db()
  return main.app


@pytest.fixture()
def client(app):
  import mcp_server
  mcp_server.reset_rate_limits()
  return TestClient(app)


def _signup(client: TestClient, email: str) -> dict:
  r = client.post("/signup", json={"email": email, "password": "password123", "name": "Test"})
  assert r.status_code == 200, r.text
  return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def signup():
  return _signup


FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 200
