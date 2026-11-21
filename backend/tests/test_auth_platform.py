"""Guest account security, dashboard access and writing aggregation."""
import json
from datetime import datetime, timedelta

import auth
from auth import DEMO_EMAIL
from models import TcfWritingSession
from routers.performance_routes import summarize_writing_sessions


def _touch_guest(client):
  # Any guest request creates/secures the shared demo account.
  client.post("/learn/session/save", json={"source_type": "text"})


def test_login_as_shared_guest_account_is_refused(client):
  _touch_guest(client)
  for password in ("demo_pass_123", "anything-else"):
    r = client.post("/login", json={"email": DEMO_EMAIL, "password": password})
    # 422 (email validation) or 401 (explicit refusal): never a token.
    assert r.status_code in (401, 422)
    assert "access_token" not in r.text


def test_login_route_refuses_guest_email_even_if_validation_allows_it(client, monkeypatch):
  from routers import auth_routes
  from schemas import LoginRequest

  payload = LoginRequest.model_construct(email=DEMO_EMAIL, password="demo_pass_123")
  from database import SessionLocal
  from fastapi import HTTPException

  db = SessionLocal()
  try:
    auth_routes.login(payload, db)
    raise AssertionError("login to the guest account must be refused")
  except HTTPException as exc:
    assert exc.status_code == 401
  finally:
    db.close()


def test_signup_with_guest_email_is_refused(client):
  r = client.post("/signup", json={"email": "Demo@TCF.local", "password": "password123"})
  assert r.status_code == 400


def test_old_hardcoded_guest_password_no_longer_verifies(client):
  from database import SessionLocal
  from models import User

  _touch_guest(client)
  db = SessionLocal()
  guest = db.query(User).filter(User.email == DEMO_EMAIL).first()
  assert guest is not None
  assert not auth.verify_password("demo_pass_123", guest.password_hash)
  db.close()


def test_guest_token_cannot_read_dashboard(client):
  token = auth.create_access_token(DEMO_EMAIL)
  assert client.get("/dashboard/summary", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_dashboard_requires_sign_in(client):
  assert client.get("/dashboard/summary").status_code in (401, 403)


def test_signed_in_user_gets_dashboard(client, signup):
  headers = signup(client, "dash_user@example.com")
  r = client.get("/dashboard/summary", headers=headers)
  assert r.status_code == 200
  assert r.json()["writing"]["average_score"] == 0.0


def _session(sid, scores_by_task, minutes_ago):
  def ev(scores):
    return json.dumps({"level": "B1", "scores": scores, "feedback": [], "improved_version": ""}) if scores else None

  s = TcfWritingSession(user_id=1, session_id=sid, mode="exam", is_submitted=True)
  s.id = int(sid[1:])
  s.task1_evaluation, s.task2_evaluation, s.task3_evaluation = (ev(x) for x in scores_by_task)
  s.updated_at = datetime.utcnow() - timedelta(minutes=minutes_ago)
  return s


def test_writing_aggregation_averages_all_three_tasks():
  full = {"structure": 6, "grammar": 6, "coherence": 6, "vocab": 6}
  high = {"structure": 9, "grammar": 9, "coherence": 9, "vocab": 9}
  sessions = [
    _session("s1", (full, full, high), 1),   # (6+6+9)/3 = 7
    _session("s2", (high, None, None), 2),   # 9
    _session("s3", (None, None, None), 3),   # ignored: no evaluation
  ]
  average, recent = summarize_writing_sessions(sessions)
  assert [r.id for r in recent] == [1, 2]
  assert recent[0].average_score == 7.0
  assert average == 8.0


def test_dashboard_reads_tcf_writing_sessions(client, signup):
  from database import SessionLocal
  from models import User

  headers = signup(client, "writer@example.com")
  db = SessionLocal()
  user = db.query(User).filter(User.email == "writer@example.com").first()
  scores = {"structure": 8, "grammar": 8, "coherence": 8, "vocab": 8}
  evaluation = json.dumps({"level": "B2", "scores": scores, "feedback": [], "improved_version": ""})
  db.add(TcfWritingSession(
    user_id=user.id, session_id="dash-writing-1", mode="exam", is_submitted=True,
    task1_evaluation=evaluation, task2_evaluation=evaluation, task3_evaluation=evaluation,
  ))
  db.commit()
  db.close()
  body = client.get("/dashboard/summary", headers=headers).json()
  assert body["writing"]["average_score"] == 8.0
  assert len(body["writing"]["recent_submissions"]) == 1


def test_health_caches_probe_and_reports_pregen(client, monkeypatch):
  import main

  monkeypatch.setenv("GEMINI_API_KEY", "fake")
  calls = []
  monkeypatch.setattr(main, "_health_probe", {"checked_at": 0.0, "result": "untested"})

  class FakeModels:
    def generate_content(self, **_kw):
      calls.append(1)
      return type("R", (), {"text": "ok"})()

  class FakeClient:
    def __init__(self, **_kw):
      self.models = FakeModels()

  import google.genai
  monkeypatch.setattr(google.genai, "Client", FakeClient)
  first = client.get("/api/health").json()
  second = client.get("/api/health").json()
  assert first["gemini_chat_test"] == "ok" and second["gemini_chat_test"] == "ok"
  assert len(calls) == 1, "the live Gemini probe must be cached"
  assert "pregen" in first
