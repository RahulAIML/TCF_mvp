"""
Live check that C1/C2 answers cannot be spotted from the options alone, and that questions vary.

Usage:  python -I backend/qa/live_guessability.py [BASE_URL] [N_PER_LEVEL]
Uses only the public API output (no model calls of its own).
"""
import json
import re
import sys
import time
import unicodedata
import urllib.request
import uuid
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
SESSION = f"qa-guess-{uuid.uuid4().hex[:8]}"
LETTERS = "ABCD"
NAME_RE = re.compile(r"^\s*(?:[-–—]\s*)?([A-ZÀ-Ý][a-zà-ÿ'’]+(?:-[A-ZÀ-Ý][a-zà-ÿ'’]+)?)\s*:", re.M)


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=150) as r:
        return json.loads(r.read())


def fold(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()


def strip(option):
    return re.sub(r"^\s*[A-D]\s*[.)]\s*", "", option).strip()


items = []
for level in ("C1", "C2"):
    qnum = {"C1": 32, "C2": 37}[level]
    for i in range(N):
        for kind, path, body in (
            ("listening", "/tcf/generate-listening-question",
             {"question_number": qnum, "session_id": SESSION, "defer_audio": True, "target_level": level}),
            ("reading", "/tcf/generate-question",
             {"question_number": qnum, "session_id": SESSION, "target_level": level}),
        ):
            t0 = time.time()
            try:
                data = post(path, body)
            except Exception as error:  # noqa: BLE001
                print(f"{kind:9} {level} #{i}: ERROR {error}")
                continue
            items.append((kind, level, data, time.time() - t0))

results = []


def record(name, ok, detail):
    results.append((name, ok, detail))


for kind in ("listening", "reading"):
    group = [d for k, _, d, _ in items if k == kind]
    if not group:
        record(f"{kind}: items fetched", False, "none")
        continue
    record(f"{kind}: items fetched", len(group) >= 2 * N * 0.9, f"{len(group)}/{2 * N}")

    longest = 0
    for d in group:
        opts = [strip(o) for o in d["options"]]
        idx = LETTERS.index(d["correct_answer"])
        lengths = [len(o) for o in opts]
        if lengths[idx] == max(lengths) and lengths.count(max(lengths)) == 1:
            longest += 1
    share = longest / len(group)
    record(f"{kind}: correct option is the unique longest", share <= 0.40, f"{longest}/{len(group)} ({share:.0%})")

    stems = [" ".join(fold(d["question"]).split()[:5]) for d in group]
    distinct = len(set(stems))
    record(f"{kind}: distinct question openings", distinct >= 0.8 * len(group), f"{distinct}/{len(group)}")
    banned = sum("position reelle" in fold(d["question"]) for d in group)
    record(f"{kind}: no 'position réelle' stems", banned == 0, f"{banned} found")

    letters = Counter(d["correct_answer"] for d in group)
    worst = max(letters.values()) / len(group)
    record(f"{kind}: letter spread", worst <= 0.40, dict(sorted(letters.items())))

per_item = [set(m.group(1) for m in NAME_RE.finditer(d.get("script", ""))) for k, _, d, _ in items if k == "listening"]
name_items = Counter(n for s in per_item for n in s)
repeated = {n: c for n, c in name_items.items() if c > 1}
record("listening: names not reused across items", len(repeated) <= 2, repeated or "none")

times = sorted(t for *_, t in items)
if times:
    record("median response time", times[len(times) // 2] < 3.0, f"{times[len(times) // 2]:.1f}s")

print()
print("=" * 78)
width = max(len(r[0]) for r in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
print("=" * 78)
passed = sum(ok for _, ok, _ in results)
print(f"{passed}/{len(results)} checks passed against {BASE}")
sys.exit(0 if passed == len(results) else 1)
