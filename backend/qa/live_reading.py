"""
Live QA for the reading module against a running backend.

    python -I backend/qa/live_reading.py https://tcf-mvp.onrender.com [--per-level 4] [--quizzes 1]

Checks per level (A1..C2): generation succeeds, question_type matches the level, no duplicate texts,
answer-letter distribution, explanation never contradicts the key (no option letters cited),
4 distinct options, text length within the level band, timings. Exam mode: same session + same
question number is stable, different sessions differ. Passage quiz: 10 questions, unique passages.
Prints a PASS/FAIL table and exits non-zero on any failure.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
RANGES = {"A1": (1, 4), "A2": (5, 10), "B1": (11, 19), "B2": (20, 29), "C1": (30, 35), "C2": (36, 39)}
WORDS = {"A1": (15, 30), "A2": (30, 60), "B1": (70, 110), "B2": (120, 170), "C1": (170, 220), "C2": (200, 250)}
LETTER_CITE = re.compile(r"\b(option|réponse|reponse|proposition|choix|lettre)s?\s+\(?[A-D]\)?(?![\w'])", re.I)
JARGON = re.compile(r"aporie|herméneutique|épistémolog|paradigm|rhodanien", re.I)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def post(base: str, path: str, body: dict, timeout: float = 150) -> tuple[dict | None, float, str | None]:
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code}: {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return None, time.time() - t0, str(e)


def check_question(level: str, q: dict) -> list[str]:
    problems = []
    if q.get("question_type") != f"reading_{level.lower()}":
        problems.append(f"type {q.get('question_type')}")
    opts = [re.sub(r"^[A-D]\.\s*", "", o).strip().lower() for o in q.get("options", [])]
    if len(opts) != 4 or len(set(opts)) != 4:
        problems.append("options not 4 distinct")
    if q.get("correct_answer") not in ("A", "B", "C", "D"):
        problems.append("bad key")
    if LETTER_CITE.search(q.get("explanation", "")):
        problems.append("explanation cites a letter")
    words = len(re.findall(r"\w+", q.get("text", "")))
    low, high = WORDS[level]
    if words < low * 0.5 or words > high * 1.8:
        problems.append(f"length {words} words")
    if level in ("C1", "C2") and JARGON.search(q.get("text", "")):
        problems.append("academic jargon")
    return problems


def run_level(base: str, level: str, n: int) -> dict:
    session = f"qa-{uuid.uuid4()}"
    start, end = RANGES[level]
    items, times, errors = [], [], []
    for i in range(n):
        data, t, err = post(base, "/tcf/generate-question",
                            {"question_number": start + (i % (end - start + 1)), "session_id": session, "target_level": level})
        times.append(t)
        if err:
            errors.append(err)
        else:
            items.append(data)
    return {"level": level, "items": items, "times": times, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--per-level", type=int, default=4)
    parser.add_argument("--quizzes", type=int, default=1)
    args = parser.parse_args()
    base = args.base_url

    print(f"Reading live QA against {base}\n")
    with ThreadPoolExecutor(3) as pool:
        level_runs = list(pool.map(lambda lvl: run_level(base, lvl, args.per_level), LEVELS))

    all_texts: list[str] = []
    letters: Counter = Counter()
    all_times: list[float] = []
    for run in level_runs:
        level = run["level"]
        problems = []
        for q in run["items"]:
            problems += check_question(level, q)
            letters[q["correct_answer"]] += 1
            all_texts.append(q["text"].strip().lower())
        all_times += run["times"]
        ok = not run["errors"] and not problems and len(run["items"]) == args.per_level
        detail = f"{len(run['items'])}/{args.per_level} ok, avg {statistics.mean(run['times']):.1f}s"
        if run["errors"]:
            detail += f", errors: {run['errors'][:2]}"
        if problems:
            detail += f", problems: {sorted(set(problems))}"
        record(f"level {level}", ok, detail)
        for q in run["items"][:1]:
            print(f"--- {level} sample: {q['question']}\n    {q['text'][:220]}…\n")

    record("no duplicate texts across all levels", len(all_texts) == len(set(all_texts)),
           f"{len(all_texts)} texts, {len(set(all_texts))} unique")
    total = sum(letters.values())
    # 3-sigma binomial band around n/4: catches real bias without flagging normal small-sample noise.
    sigma = (total * 0.25 * 0.75) ** 0.5
    low, high = total * 0.25 - 3 * sigma, total * 0.25 + 3 * sigma
    spread_ok = total == 0 or all(low <= letters[l] <= high for l in "ABCD")
    record("answer letters uniformly spread (3-sigma)", spread_ok,
           f"{dict(letters)} band {max(low, 0):.1f}–{high:.1f}")

    session = f"qa-exam-{uuid.uuid4()}"
    a, _, e1 = post(base, "/tcf/generate-question", {"question_number": 12, "session_id": session})
    b, _, e2 = post(base, "/tcf/generate-question", {"question_number": 12, "session_id": session})
    c, _, e3 = post(base, "/tcf/generate-question", {"question_number": 12, "session_id": f"qa-other-{uuid.uuid4()}"})
    record("exam: stable within session, unique across sessions",
           not (e1 or e2 or e3) and a and b and c and a["text"] == b["text"] and a["text"] != c["text"]
           and a["question_type"] == "reading_b1",
           (e1 or e2 or e3 or "")[:120])

    bad, _, err = post(base, "/tcf/generate-question", {"question_number": 3, "target_level": "Z9"})
    record("invalid level rejected (422)", err is not None and "422" in err, err or "accepted")

    passages = []
    for level in ["B1", "C1"][: max(1, args.quizzes * 2)]:
        quiz, t, err = post(base, "/generate-passage-quiz", {"level": level, "session_id": f"qa-{uuid.uuid4()}"})
        ok = err is None and quiz and len(quiz["questions"]) == 10 and not any(
            LETTER_CITE.search(q["explanation"]) for q in quiz["questions"])
        if quiz:
            passages.append(quiz["passage"])
        record(f"passage quiz {level}", bool(ok), f"{t:.1f}s {err or ''}")
    record("passages unique", len(passages) == len(set(passages)), f"{len(passages)} passages")

    print(f"\n{'CHECK':<55} RESULT  DETAIL")
    for name, ok, detail in results:
        print(f"{name:<55} {'PASS' if ok else 'FAIL'}    {detail}")
    if all_times:
        print(f"\nTimings: min {min(all_times):.1f}s, median {statistics.median(all_times):.1f}s, max {max(all_times):.1f}s")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
