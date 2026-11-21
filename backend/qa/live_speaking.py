"""
Live QA for speaking, pronunciation, vocabulary and TTS against a running backend.

Usage:  python -I backend/qa/live_speaking.py [BASE_URL]
        (default BASE_URL: https://tcf-mvp.onrender.com)
Uses only generated test data (a silent WAV, fixed French sentences); no personal data.
"""
from __future__ import annotations

import io
import json
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
TIMEOUT = 150
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def request(method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, method=method, headers=headers or {})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(), dict(resp.headers), time.time() - start
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers), time.time() - start


def post_json(path: str, payload: dict):
    return request("POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"})


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for name, (filename, content, ctype) in files.items():
        out.write(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        out.write(content)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def silent_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


def sse_events(raw: bytes) -> list[dict]:
    events = []
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("data: ") and line.strip() != "data: [DONE]":
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def check_silence() -> None:
    body, ctype = multipart({"language": "fr"}, {"audio": ("silence.wav", silent_wav(), "audio/wav")})
    status, raw, _, secs = request("POST", "/tcf/transcribe-audio", body, {"Content-Type": ctype})
    data = json.loads(raw or b"{}") if status == 200 else {}
    record("transcribe: silence gives no invented text", status == 200 and data.get("transcript") == "",
           f"HTTP {status} in {secs:.1f}s, transcript={data.get('transcript')!r}, no_speech={data.get('no_speech')}")

    body, ctype = multipart({"target_text": "Bonjour, comment allez-vous ?", "language": "fr"},
                            {"audio_file": ("silence.wav", silent_wav(), "audio/wav")})
    status, raw, _, secs = request("POST", "/api/pronunciation/evaluate", body, {"Content-Type": ctype})
    data = json.loads(raw or b"{}") if status == 200 else {}
    record("pronunciation: silence is not scored", status == 200 and data.get("user_text") == "" and data.get("accuracy") == 0,
           f"HTTP {status} in {secs:.1f}s, user_text={data.get('user_text')!r}, accuracy={data.get('accuracy')}")

    status, raw, _, secs = request("POST", "/api/pronunciation/evaluate/stream", body, {"Content-Type": ctype})
    kinds = [e.get("type") for e in sse_events(raw)] if status == 200 else []
    record("pronunciation stream: silence", status == 200 and kinds == ["no_speech"], f"HTTP {status} in {secs:.1f}s, events={kinds}")


def check_tts_voices() -> None:
    status, raw, _, _ = request("GET", "/api/tts/voices?language=fr")
    voices = json.loads(raw) if status == 200 else []
    record("tts: 4 French voices listed", status == 200 and len(voices) == 4, f"HTTP {status}, {[v.get('id') for v in voices]}")
    for voice in voices:
        start = time.time()
        status, raw, _, _ = post_json("/api/tts/generate", {"text": "Bonjour, je suis votre voix de test.", "voice_id": voice["id"]})
        if status != 200:
            record(f"tts: {voice['id']}", False, f"start HTTP {status}")
            continue
        job_id = json.loads(raw)["job_id"]
        job = {}
        while time.time() - start < 120:
            time.sleep(2)
            s, r, _, _ = request("GET", f"/api/tts/job/{job_id}")
            job = json.loads(r) if s == 200 else {"status": f"HTTP {s}"}
            if job.get("status") in ("done", "error") or s != 200:
                break
        url = job.get("audio_url")
        head_status, ctype = None, ""
        if url:
            head_status, _, headers, _ = request("HEAD", url)
            ctype = headers.get("content-type", headers.get("Content-Type", ""))
        ok = job.get("status") == "done" and head_status == 200 and ctype.startswith("audio/")
        record(f"tts: {voice['id']} ({voice.get('gender')}) end to end", ok,
               f"status={job.get('status')} in {time.time() - start:.1f}s, HEAD {head_status} {ctype}")
    status, _, _, _ = post_json("/api/tts/generate", {"text": "Bonjour", "voice_id": "xx-XX-robot-9"})
    record("tts: unknown voice rejected", status == 400, f"HTTP {status}")


def check_vocabulary() -> None:
    session = f"qa-{uuid.uuid4().hex[:10]}"
    words: list[str] = []
    timings = []
    for i in range(4):
        status, raw, _, secs = post_json("/api/pronunciation/vocabulary/generate",
                                         {"level": "B1", "count": 8, "language": "fr", "session_id": session})
        timings.append(secs)
        if status != 200:
            record(f"vocabulary: set {i + 1}", False, f"HTTP {status}: {raw[:120]!r}")
            return
        words += [w["word"].lower() for w in json.loads(raw)["words"]]
    dupes = len(words) - len(set(words))
    record("vocabulary: 4 sets, no word repeated in the session", dupes == 0 and len(words) == 32,
           f"{len(words)} words, {dupes} repeats, times={[f'{t:.1f}s' for t in timings]}")
    status, raw, _, _ = post_json("/api/pronunciation/vocabulary/generate", {"level": "A2", "count": 99, "session_id": session})
    count = json.loads(raw).get("count") if status == 200 else None
    record("vocabulary: count clamped to 20", status == 200 and count == 20, f"HTTP {status}, count={count}")


def check_guide() -> None:
    status, raw, headers, secs = request("GET", "/api/pronunciation/guide/bonjour?language=fr")
    ctype = headers.get("content-type", headers.get("Content-Type", ""))
    record("pronunciation guide audio", status == 200 and ctype.startswith("audio/") and len(raw) > 1000,
           f"HTTP {status} {ctype} {len(raw)} bytes in {secs:.1f}s")
    status, _, _, secs2 = request("GET", "/api/pronunciation/guide/bonjour?language=fr")
    record("pronunciation guide cached on repeat", status == 200 and secs2 < max(1.5, secs), f"{secs2:.2f}s vs {secs:.2f}s")


def check_conversation() -> None:
    for task in ("basic_interaction", "role_play", "opinion"):
        status, raw, _, secs = post_json("/tcf/speaking/opening", {"task_type": task})
        data = json.loads(raw) if status == 200 else {}
        ok = status == 200 and len(data.get("reply", "")) > 15 and "[" not in data.get("reply", "") and bool(data.get("audio_url"))
        record(f"opening {task}", ok, f"HTTP {status} in {secs:.1f}s, topic={str(data.get('session_topic'))[:70]!r}")

    history = [{"role": "assistant", "content": "Bonjour, je m'appelle Marie Dupont. Que pensez-vous du télétravail ?"}]
    payload = {
        "message": "Je pense que le télétravail est pratique parce qu'on gagne du temps, mais on se sent parfois isolé.",
        "history": history, "task_type": "opinion", "session_topic": "Le télétravail", "examiner_name": "Marie Dupont",
    }
    status, raw, _, secs = post_json("/tcf/conversation/stream", payload)
    events = sse_events(raw) if status == 200 else []
    kinds = [e.get("type") for e in events]
    reply = next((e.get("reply") for e in events if e.get("type") == "reply"), "")
    audio = next((e.get("audio_url") for e in events if e.get("type") == "audio"), None)
    record("conversation stream: tokens, reply, audio", status == 200 and "token" in kinds and bool(reply) and bool(audio),
           f"HTTP {status} in {secs:.1f}s, {kinds.count('token')} tokens, reply={reply[:60]!r}")

    eval_history = history + [{"role": "user", "content": payload["message"]}]
    status, raw, _, secs = post_json("/tcf/evaluate/stream", {"history": eval_history, "task_type": "opinion"})
    events = sse_events(raw) if status == 200 else []
    scores = next((e for e in events if e.get("type") == "scores"), {})
    model = "".join(e.get("token", "") for e in events if e.get("type") == "token")
    record("evaluation stream: scores + model answer", status == 200 and "fluency" in scores and len(model) > 40,
           f"HTTP {status} in {secs:.1f}s, cefr={scores.get('cefr_level')}, scores={[scores.get(k) for k in ('fluency', 'grammar', 'vocabulary', 'interaction')]}")


def main() -> int:
    print(f"Live speaking QA against {BASE_URL}\n")
    for check in (check_silence, check_tts_voices, check_vocabulary, check_guide, check_conversation):
        print(f"[{check.__name__}]")
        try:
            check()
        except Exception as error:
            record(check.__name__, False, f"crashed: {error}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 78)
    print(f"{'RESULT':6}  {'CHECK':48}  DETAIL")
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL':6}  {name[:48]:48}  {detail[:110]}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
