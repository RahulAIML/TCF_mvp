"""
Live QA for Writing, AI chat and Phrase Helper against a running backend.

  python -I backend/qa/live_writing.py [BASE_URL]     (default https://tcf-mvp.onrender.com)

Checks task-set uniqueness and latency (pre-generation pool), evaluation honesty (weak vs strong on-topic
text), first-token latency of every streaming endpoint, and French-in → French-out in the chat.
Prints a PASS/FAIL table; exit code 1 if anything fails.
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
TIMEOUT = 150
FIRST_TOKEN_TARGET = 3.0  # seconds; brief asks for ~1-2 s, allow network margin
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def post_json(path: str, body: dict) -> tuple[dict | None, float, str | None]:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read()), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, f"HTTP {e.code} {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return None, time.time() - t0, str(e)


def post_sse(path: str, body: dict) -> tuple[list, float | None, float, str | None]:
    """Returns (events, first_token_seconds, total_seconds, error)."""
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0, first, events = time.time(), None, []
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if first is None and event.get("token"):
                    first = time.time() - t0
                events.append(event)
        return events, first, time.time() - t0, None
    except Exception as e:  # noqa: BLE001
        return events, first, time.time() - t0, str(e)


def tokens(events: list) -> str:
    return "".join(e.get("token", "") for e in events)


def avg_score(evaluation: dict) -> float:
    s = evaluation["scores"]
    return sum(s.values()) / len(s)


FRENCH_WORDS = {"le", "la", "les", "des", "est", "une", "pour", "avec", "dans", "que", "qui", "vous", "on"}


def looks_french(text: str) -> bool:
    words = [w.strip(".,;:!?«»()").lower() for w in text.split()]
    return sum(w in FRENCH_WORDS for w in words) >= 3


# 1. Task sets: unique and fast (served from the pre-generated pool after warm-up).
sets, times = [], []
for i in range(5):
    data, t, err = post_json("/tcf/generate-writing-tasks", {"session_id": "qa-writing"})
    times.append(t)
    if err:
        record(f"task set #{i + 1}", False, err)
        continue
    sets.append(data)
prompts = [p for s in sets for p in s.values()]
record("task sets generated", len(sets) == 5, f"{len(sets)}/5, times {', '.join(f'{t:.1f}s' for t in times)}")
record("no repeated prompt", len(prompts) == len(set(prompts)), f"{len(set(prompts))} unique of {len(prompts)}")
record("task 3 includes two documents", all("Document 1" in s["task3_prompt"] and "Document 2" in s["task3_prompt"] for s in sets),
       "Document 1 / Document 2 present" if sets else "no sets")
warm = sorted(times)[len(times) // 2] if times else 99
record("task set latency (median)", warm < 3.0, f"{warm:.1f}s (pool should make this near-instant)")

# 2. Evaluation honesty: weak vs strong on-topic text for the same Task 1 prompt.
task1 = sets[0]["task1_prompt"] if sets else "Écrivez un message à votre voisine Claire pour l'inviter à un repas de quartier samedi."
WEAK = ("Bonjour Claire. Je suis invite toi a le repas samedi. Il y a beaucoup manger. Tu viens ? "
        "C'est bien. Moi aussi je fais un gateau. Le repas il est a midi dans le parc. Merci. "
        "Je suis content si tu viens avec ton mari. A samedi. Au revoir. Marc")
STRONG = ("Chère Claire,\n\nJe me permets de t'écrire pour t'inviter au repas de quartier que nous organisons samedi "
          "prochain, à partir de midi, dans le parc situé au bout de notre rue. Chaque voisin apportera un plat à "
          "partager : pour ma part, je préparerai une tarte aux pommes. Ce sera l'occasion de faire connaissance avec "
          "les nouvelles familles arrivées cet automne et de passer un moment convivial. Si tu le souhaites, ton mari "
          "et tes enfants sont évidemment les bienvenus. Pourrais-tu me confirmer ta présence d'ici jeudi afin que je "
          "puisse prévoir assez de chaises ?\n\nAu plaisir de te voir samedi,\nMarc")
evals = {}
for name, text in (("weak", WEAK), ("strong", STRONG)):
    data, t, err = post_json("/tcf/evaluate-writing", {"task_type": "task1", "prompt": task1, "response_text": text})
    if err:
        record(f"evaluate {name}", False, err)
        continue
    evals[name] = data
    record(f"evaluate {name}", True, f"level {data['level']}, scores {data['scores']}, {t:.1f}s")
if len(evals) == 2:
    gap = avg_score(evals["strong"]) - avg_score(evals["weak"])
    record("score separation weak vs strong", gap >= 2.0, f"strong {avg_score(evals['strong']):.1f} vs weak {avg_score(evals['weak']):.1f}")
    record("weak text not flattered", avg_score(evals["weak"]) <= 5.0, f"weak avg {avg_score(evals['weak']):.1f}/10")

# 3. Streaming endpoints: first-token latency.
streams = [
    ("chat stream (FR)", "/api/ai/chat/stream", {"message": "Quelle est la différence entre « depuis » et « pendant » ?"}),
    ("writing assistant stream", "/tcf/writing/assistant/stream", {"message": "Je suis allé au magasin hier et j'ai acheté des pomme.", "action": "grammar"}),
    ("explain-text stream", "/explain-text/stream", {"text": "au fur et à mesure"}),
    ("translate stream", "/translate/stream", {"text": "Je vous écris pour vous inviter au repas de quartier.", "direction": "fr-en"}),
    ("evaluate stream", "/tcf/evaluate-writing/stream", {"task_type": "task1", "prompt": task1, "response_text": STRONG}),
]
stream_text = {}
for name, path, body in streams:
    events, first, total, err = post_sse(path, body)
    errors = [e["error"] for e in events if "error" in e]
    ok = err is None and not errors and first is not None and first <= FIRST_TOKEN_TARGET
    stream_text[name] = tokens(events)
    detail = err or (errors[0] if errors else f"first token {first:.2f}s, total {total:.1f}s" if first is not None else "no tokens")
    record(f"{name} first token", ok, detail)
    if name == "evaluate stream":
        final = [e["evaluation"] for e in events if "evaluation" in e]
        record("evaluate stream final result", bool(final), str(final[0]["scores"]) if final else "missing")

# 4. Language matching.
record("chat answers French in French", looks_french(stream_text.get("chat stream (FR)", "")),
       stream_text.get("chat stream (FR)", "")[:80].replace("\n", " "))
events, _, _, err = post_sse("/api/ai/chat/stream", {"message": "What does 'au fur et à mesure' mean?"})
english = tokens(events)
record("chat answers English in English", not looks_french(english) and bool(english), english[:80].replace("\n", " "))
events, _, _, err = post_sse("/api/ai/chat/stream", {"message": "Pourquoi le CO2 réchauffe-t-il la planète ?"})
co2 = tokens(events)
record("chat uses no LaTeX", "$" not in co2 and "\\text" not in co2 and "_{" not in co2, "CO₂ in Unicode" if "CO₂" in co2 else co2[:80])

# 5. Submit: three tasks evaluated in parallel, streamed.
if sets:
    s = sets[0]
    t0 = time.time()
    events, first, total, err = post_sse("/tcf/writing/submit/stream", {
        "session_id": f"qa-{int(t0)}", "mode": "exam",
        "task1_prompt": s["task1_prompt"], "task2_prompt": s["task2_prompt"], "task3_prompt": s["task3_prompt"],
        "task1_text": STRONG, "task2_text": STRONG, "task3_text": STRONG,
    })
    done = {e["task"] for e in events if "evaluation" in e}
    record("submit stream: 3 evaluations", done == {"task1", "task2", "task3"} and err is None,
           f"{sorted(done)}, first token {first or 0:.2f}s, total {total:.1f}s")
    record("submit stream saved", {"saved": True} in events, "saved" if {"saved": True} in events else "not saved")

print("\n" + "=" * 70)
failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL':4}  {name:40} {detail[:60]}")
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed against {BASE}")
sys.exit(1 if failed else 0)
