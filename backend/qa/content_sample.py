"""Sample live listening and reading items and flag structural problems.

This does not judge whether the keyed answer is the one a teacher would pick. It checks the
constraints the product promises: four options, one key, the level matches the question number,
the explanation does not name a letter, a Canadian scene is not priced in francs, and the correct
option is not the only critical or the only long one.

    python -m qa.content_sample https://tcf-mvp.onrender.com --each 102
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import quality_guard

BANDS = {"A1": (1, 4), "A2": (5, 10), "B1": (11, 19), "B2": (20, 29), "C1": (30, 35), "C2": (36, 39)}
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def _post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Learner-Id": "content-qa-learner-2222"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode())


def _problems(kind: str, level: str, number: int, item: dict) -> list[str]:
    problems: list[str] = []
    options = item.get("options") or []
    if len(options) != 4:
        problems.append(f"{len(options)} options")
    letter = item.get("correct_answer")
    if letter not in ("A", "B", "C", "D"):
        problems.append(f"bad key {letter!r}")
    bodies = [quality_guard.option_body(option) for option in options]
    if len(bodies) == 4 and len(set(body.lower() for body in bodies)) < 4:
        problems.append("duplicate options")
    low, high = BANDS[level]
    if not (low <= number <= high):
        problems.append(f"question {number} is outside {level}")
    if item.get("level") and item["level"] != level:
        problems.append(f"returned level {item['level']}")
    problems.extend(quality_guard.explanation_problems(item.get("explanation") or ""))
    problems.extend(quality_guard.choice_problems(level, options, letter or "A"))
    text = " ".join([
        item.get("script") or "",
        item.get("text") or "",
        item.get("question") or "",
        " ".join(options),
    ])
    if quality_guard.anachronism_problems(text):
        problems.append("francs in a Canadian scene")
    passage = item.get("script") or item.get("text") or ""
    words = len(passage.split())
    if words < 8:
        problems.append(f"passage too short ({words} words)")
    if kind == "listening" and len(item.get("speakers") or []) >= 2:
        for name in item["speakers"]:
            if name not in passage:
                problems.append(f"speaker {name} missing from script")
                break
    return problems


def _one(base: str, kind: str, index: int) -> tuple[str, str, int, list[str], str]:
    level = LEVELS[index % 6]
    number = {"A1": 2, "A2": 7, "B1": 15, "B2": 24, "C1": 32, "C2": 37}[level]
    if kind == "listening":
        item = _post(base, "/tcf/generate-listening-question", {
            "question_number": number, "target_level": level, "defer_audio": True,
            "session_id": f"content-qa-l-{index}",
        })
    else:
        item = _post(base, "/tcf/generate-question", {
            "question_number": number, "target_level": level, "session_id": f"content-qa-r-{index}",
        })
    return kind, level, number, _problems(kind, level, number, item), item.get("correct_answer") or "?"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", nargs="?", default="https://tcf-mvp.onrender.com")
    parser.add_argument("--each", type=int, default=102)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    jobs = [("listening", i) for i in range(args.each)] + [("reading", i) for i in range(args.each)]
    bad: list[str] = []
    letters: Counter[str] = Counter()
    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_one, args.base, kind, index) for kind, index in jobs]
        for future in as_completed(futures):
            try:
                kind, level, number, problems, letter = future.result()
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as error:
                failed += 1
                print(f"REQUEST FAIL {error}", flush=True)
                continue
            letters[letter] += 1
            if problems:
                bad.append(f"{kind} {level} Q{number}: {', '.join(problems)}")
                print(bad[-1], flush=True)
            else:
                ok += 1
                if ok % 20 == 0:
                    print(f"ok {ok}", flush=True)
    print(f"\nchecked {ok + len(bad)}  ok {ok}  flagged {len(bad)}  request_failures {failed}")
    print("answer letters", dict(letters))
    for line in bad[:40]:
        print(" ", line)
    return 1 if bad or failed else 0


if __name__ == "__main__":
    sys.exit(main())
