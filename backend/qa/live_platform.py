"""
Live QA for the platform modules (health, AI Learn, guest routes). Guest only: never logs in or signs up.

Usage:
  python -I backend/qa/live_platform.py [BASE_URL] [FRONTEND_URL]
  defaults: https://tcf-mvp.onrender.com  https://tcf-trainer.onrender.com
Exit code 0 when every check passes.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
FRONTEND_URL = (sys.argv[2] if len(sys.argv) > 2 else "https://tcf-trainer.onrender.com").rstrip("/")
TIMEOUT = 150

SAMPLE_TEXT = (
    "Depuis le printemps, la ville de Québec prête gratuitement des vélos électriques aux habitants "
    "qui s'engagent à laisser leur voiture au garage deux jours par semaine. Les premiers résultats "
    "sont encourageants : la circulation a baissé de huit pour cent dans le centre, mais certains "
    "commerçants craignent une baisse de leur clientèle venue des banlieues."
)

FRONTEND_ROUTES = [
    "/", "/login", "/register", "/tcf", "/tcf/learn", "/tcf/reading", "/tcf/reading-practice", "/tcf/mock-exam",
    "/tcf/passage-analyzer", "/tcf/listening-exam", "/tcf/speaking", "/tcf/writing", "/tcf/pronunciation",
    "/tcf/vocabulary", "/tcf/tts", "/tcf/grok", "/tcf/dashboard",
]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def request(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def post_json(path: str, body: dict):
    t0 = time.time()
    try:
        with request("POST", BASE_URL + path, body) as r:
            return json.loads(r.read()), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code}: {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return None, time.time() - t0, str(e)


def check_health() -> None:
    t0 = time.time()
    try:
        with request("GET", BASE_URL + "/api/health") as r:
            body = json.loads(r.read())
        elapsed = time.time() - t0
        ok = body.get("gemini_chat_test") == "ok" and "pregen" in body
        record("health", ok, f"{elapsed:.1f}s gemini={body.get('gemini_chat_test')} pregen_pools={len(body.get('pregen', {}))}")
        t1 = time.time()
        with request("GET", BASE_URL + "/api/health") as r:
            r.read()
        record("health probe cached", time.time() - t1 < 3, f"second call {time.time() - t1:.2f}s")
    except Exception as e:  # noqa: BLE001
        record("health", False, str(e))


def check_learn() -> None:
    t0 = time.time()
    first_event = None
    events: list[dict] = []
    try:
        with request("POST", BASE_URL + "/learn/analyze/stream", {"text": SAMPLE_TEXT}) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                if first_event is None:
                    first_event = time.time() - t0
                events.append(json.loads(line[6:]))
    except Exception as e:  # noqa: BLE001
        record("learn analyze stream", False, str(e))
        return
    total = time.time() - t0
    kinds = [e.get("type") for e in events]
    overview = next((e for e in events if e.get("type") == "overview"), None)
    exercise_event = next((e for e in events if e.get("type") == "exercises"), None)
    done = next((e for e in events if e.get("type") == "done"), None)
    record(
        "learn analyze stream",
        bool(overview and exercise_event and done),
        f"first event {first_event or 0:.1f}s, total {total:.1f}s, events={kinds}",
    )
    if not (overview and exercise_event and done):
        return
    record("learn first event under 15s", (first_event or 99) < 15, f"{first_event:.1f}s")
    exercises = exercise_event["exercises"]
    record("learn 5 exercises", len(exercises) == 5, f"types={[e['type'] for e in exercises]}")

    mcq = next((e for e in exercises if e["type"] == "mcq"), None)
    if mcq:
        wrong = next(letter for letter in "ABCD" if not mcq.get("correct_answer", "").upper().startswith(letter))
        ev, elapsed, err = post_json("/learn/evaluate", {
            "exercise_type": "mcq", "question": mcq["question"], "correct_answer": mcq.get("correct_answer", ""),
            "user_answer": wrong, "explanation": mcq.get("explanation"),
        })
        ok = ev is not None and ev["is_correct"] is False and elapsed < 3 and "incorrecte" in " ".join(ev["feedback"]).lower()
        record("learn MCQ evaluate instant + French", ok, err or f"{elapsed:.2f}s feedback={ev['feedback']}")

    asked = [e["question"] for e in exercises]
    time.sleep(25)  # let the pre-generated batch finish
    body = {"topic": overview["topic"], "level": overview["level"], "summary": overview["summary"],
            "content_id": done.get("content_id"), "exclude_questions": asked}
    more, elapsed, err = post_json("/learn/more-exercises", body)
    if more is None:
        record("learn more-exercises instant", False, err or "no data")
        return
    record("learn more-exercises instant", elapsed < 4, f"{elapsed:.2f}s, {len(more)} exercises")
    new_questions = [e["question"] for e in more]
    repeats = set(map(str.lower, new_questions)) & set(map(str.lower, asked))
    record("learn more-exercises unique", not repeats and len(new_questions) == len(set(new_questions)), f"repeats={len(repeats)}")


def check_frontend_routes() -> None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: D401
            return None

    opener = urllib.request.build_opener(NoRedirect)
    for route in FRONTEND_ROUTES:
        try:
            with opener.open(FRONTEND_URL + route, timeout=60) as r:
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:  # noqa: BLE001
            record(f"page {route}", False, str(e))
            continue
        record(f"page {route}", status == 200, f"HTTP {status}")


if __name__ == "__main__":
    print(f"Platform live QA  backend={BASE_URL}  frontend={FRONTEND_URL}")
    check_health()
    check_learn()
    check_frontend_routes()
    failed = [r for r in results if not r[1]]
    print("\n| Check | Result | Detail |\n|---|---|---|")
    for name, ok, detail in results:
        print(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)
