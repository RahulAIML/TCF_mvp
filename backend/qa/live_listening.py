"""
Live QA for the listening module against a deployed backend.

    python -I backend/qa/live_listening.py [BASE_URL] [N_PER_LEVEL]

Checks per question: served without error, unique (id and script), the explanation never cites an option letter,
dialogues have >=2 labelled speakers, the audio URL answers 200 with audio. Overall: letter distribution, timings.
Exit code 1 when any check fails.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
RANGES = {"A1": 2, "A2": 7, "B1": 15, "B2": 25, "C1": 32, "C2": 38}
LETTER_REF = re.compile(r"\b(?:option|réponse|proposition|lettre)\s*\(?[A-D]\)?(?!\w)", re.IGNORECASE)
SPEAKER = re.compile(r"^\s*(?:[-–—]\s*)?([A-ZÀ-ÝÉÈ][a-zà-ÿ'’]+(?:[- ][A-ZÀ-ÝÉÈ][a-zà-ÿ'’]+)?)\s*(?:\([^)]{0,40}\))?\s*:", re.M)


def post(path, body, timeout=180):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code}: {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return None, time.time() - t0, str(e)


def audio_ok(url):
    full = url if url.startswith("http") else BASE + url
    try:
        with urllib.request.urlopen(urllib.request.Request(full, method="GET"), timeout=60) as r:
            data = r.read()
            return r.status == 200 and len(data) > 2000 and "audio" in r.headers.get("Content-Type", ""), len(data)
    except Exception:  # noqa: BLE001
        return False, 0


def main():
    session = str(uuid.uuid4())
    rows, failures = [], []
    ids, scripts, letters, times = set(), set(), Counter(), []
    for level in LEVELS:
        for i in range(N):
            q, dt, err = post("/tcf/generate-listening-question",
                              {"question_number": RANGES[level], "session_id": session, "defer_audio": True, "target_level": level})
            times.append(dt)
            if err:
                failures.append(f"{level}#{i} question: {err}")
                rows.append((level, i, f"{dt:5.1f}s", "-", "-", "-", "FAIL"))
                continue
            checks = []
            qid = q.get("question_id") or q["script"]
            if qid in ids or q["script"] in scripts:
                checks.append("duplicate")
            ids.add(qid)
            scripts.add(q["script"])
            letters[q["correct_answer"]] += 1
            if LETTER_REF.search(q.get("explanation", "")):
                checks.append("letter in explanation")
            if len({o[3:].strip().lower() for o in q["options"]}) < 4:
                checks.append("duplicate options")
            labels = {m.group(1) for m in SPEAKER.finditer(q["script"])}
            dialogue = len(q.get("speakers") or []) >= 2
            if dialogue and not set(q["speakers"]) <= labels:
                checks.append("speaker labels missing")
            audio_url, a_dt = q.get("audio_url"), 0.0
            if not audio_url:
                a, a_dt, a_err = post("/tcf/generate-listening-audio", {"script": q["script"], "speakers": q.get("speakers") or []})
                audio_url = (a or {}).get("audio_url")
                if a_err:
                    checks.append(f"audio request: {a_err}")
            ok, size = audio_ok(audio_url) if audio_url else (False, 0)
            if not ok:
                checks.append("audio not playable")
            status = "PASS" if not checks else "FAIL: " + ", ".join(checks)
            if checks:
                failures.append(f"{level}#{i}: {', '.join(checks)}")
            rows.append((level, i, f"{dt:5.1f}s", f"{a_dt:4.1f}s" if a_dt else "pool", "dialog" if dialogue else "mono",
                         q["correct_answer"], status))
            print(f"{level} #{i}  q={dt:5.1f}s  audio={'pregen' if not a_dt else f'{a_dt:.1f}s'}  "
                  f"{'dialogue ' + '/'.join(q.get('speakers') or []) if dialogue else 'monologue'}  "
                  f"ans={q['correct_answer']}  {status}", flush=True)
            print(f"      Q: {q['question'][:110]}", flush=True)

    total = sum(letters.values())
    print("\nLetter distribution:", dict(letters))
    if total >= 12:
        for letter in "ABCD":
            share = letters[letter] / total
            if not 0.1 <= share <= 0.4:
                failures.append(f"letter {letter} share {share:.0%} outside 10–40%")
    if times:
        ordered = sorted(times)
        print(f"Question time: median {ordered[len(ordered) // 2]:.1f}s, max {ordered[-1]:.1f}s")
    print(f"\nRESULT: {'PASS' if not failures else 'FAIL'} — {len(rows)} questions, {len(failures)} problems")
    for f in failures:
        print("  -", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
