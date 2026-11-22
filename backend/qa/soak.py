"""Hit the live API until a normal session would have failed if anything returns 5xx.

    PYTHONPATH=. python qa/soak.py https://tcf-mvp.onrender.com

Exits 1 when any user-visible request fails. Audio calls poll the job until the file is ready.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
NUMBERS = {"A1": 2, "A2": 7, "B1": 15, "B2": 24, "C1": 32, "C2": 37}


def _request(method: str, url: str, body: dict | None = None, timeout: float = 60) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "X-Learner-Id": "soak-learner-4444"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            try:
                return response.status, json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                return response.status, raw[:120].decode(errors="replace")
    except urllib.error.HTTPError as error:
        raw = error.read()[:200]
        return error.code, raw.decode(errors="replace")


def _audio(base: str, script: str, speakers: list[str]) -> tuple[bool, str]:
    status, payload = _request(
        "POST", base + "/tcf/generate-listening-audio",
        {"script": script, "speakers": speakers}, timeout=40,
    )
    if status >= 500:
        return False, f"audio post {status}"
    if not isinstance(payload, dict):
        return False, "audio post not json"
    url = payload.get("audio_url")
    job = payload.get("job_id")
    deadline = time.time() + 150
    while not url and job and time.time() < deadline:
        time.sleep(1.5)
        polled_status, polled = _request("GET", f"{base}/tcf/listening-audio-jobs/{job}", timeout=30)
        if polled_status >= 500:
            return False, f"audio poll {polled_status}"
        if isinstance(polled, dict):
            url = polled.get("audio_url")
            if polled.get("status") == "failed":
                return False, "audio job failed"
    if not url:
        return False, "audio never ready"
    file_status, _body = _request("GET", base + url, timeout=30)
    if file_status >= 400:
        return False, f"audio file {file_status}"
    return True, url


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://tcf-mvp.onrender.com").rstrip("/")
    failures: list[str] = []
    ok = 0

    def check(label: str, status: int, good) -> None:
        nonlocal ok
        if status >= 500 or not good:
            failures.append(f"{label} status={status}")
        else:
            ok += 1

    jobs = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i in range(40):
            jobs.append(pool.submit(_request, "GET", base + "/api/version", None, 20))
        for i in range(12):
            level = LEVELS[i % 6]
            jobs.append(pool.submit(
                _request, "POST", base + "/tcf/generate-listening-question",
                {"question_number": NUMBERS[level], "target_level": level, "defer_audio": True, "session_id": f"soak-l-{i}"},
                90,
            ))
            jobs.append(pool.submit(
                _request, "POST", base + "/tcf/generate-question",
                {"question_number": NUMBERS[level], "target_level": level, "session_id": f"soak-r-{i}"},
                90,
            ))
        for future in as_completed(jobs):
            try:
                status, payload = future.result()
            except Exception as error:
                failures.append(f"request {error}")
                continue
            good = status < 500 and (not isinstance(payload, dict) or payload.get("commit") or payload.get("script") or payload.get("text") or payload.get("options"))
            check("item", status, good)

    # Audio for every level, including a long C1 and C2 interview.
    dialogues = [
        ("A1", "Sophie : Bonjour, vous avez des cartes postales ?\nMarc : Oui, elles sont sur la table.", ["Sophie", "Marc"]),
        ("A2", "Luc : Le train de Québec part à dix heures.\nEmma : D'accord, je prends celui de dix heures quinze.", ["Luc", "Emma"]),
        ("B1", "Olivier : La direction interdit les appels dans l'espace ouvert.\nNathalie : Alors on utilisera les cabines.", ["Olivier", "Nathalie"]),
        ("B2", "Emma : Les nouveaux sièges fatiguent les collègues de Toronto.\nJean : Personne n'a montré comment les régler.", ["Emma", "Jean"]),
        ("C1", "\n".join([
            "Journaliste : Vous défendez un nouveau réseau autour des gares de Montréal. Qu'est-ce qui bloque encore ?",
            "Expert : Le plan est techniquement élégant, mais il ignore la marche et les quartiers éloignés.",
            "Journaliste : Les usagers refusent donc de laisser la voiture ?",
            "Expert : Pas seulement. Sans une desserte fine, le modèle reste une projection, pas un trajet réel.",
        ]), ["Journaliste", "Expert"]),
        ("C2", "\n".join([
            "Léa : La ville vante un guichet numérique pour les nouveaux arrivants.",
            "Claire : La belle vitrine. Sans médiateurs, ce portail devient un labyrinthe.",
            "Léa : Numériser désengorge tout de même les files.",
            "Claire : Cela déplace la charge vers des bénévoles et masque le recul du service public.",
        ]), ["Léa", "Claire"]),
    ]
    for level, script, speakers in dialogues:
        success, detail = _audio(base, script, speakers)
        if success:
            ok += 1
            print(f"audio {level} ok {detail}", flush=True)
        else:
            failures.append(f"audio {level} {detail}")
            print(f"FAIL audio {level} {detail}", flush=True)

    # More question traffic so the total crosses 300 attempts when combined with retries on the server.
    extra = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for i in range(120):
            level = LEVELS[i % 6]
            futures.append(pool.submit(
                _request, "POST", base + "/tcf/generate-listening-question",
                {"question_number": NUMBERS[level], "target_level": level, "defer_audio": True, "session_id": f"soak-l2-{i}"},
                90,
            ))
        for i in range(120):
            level = LEVELS[i % 6]
            futures.append(pool.submit(
                _request, "POST", base + "/tcf/generate-question",
                {"question_number": NUMBERS[level], "target_level": level, "session_id": f"soak-r2-{i}"},
                90,
            ))
        for future in as_completed(futures):
            extra += 1
            try:
                status, payload = future.result()
            except Exception as error:
                failures.append(str(error))
                continue
            good = status < 500 and isinstance(payload, dict) and (payload.get("script") or payload.get("text"))
            check("bulk", status, good)

    total = ok + len(failures)
    print(f"\nsoak requests={total} ok={ok} failures={len(failures)}")
    for line in failures[:30]:
        print(" ", line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
