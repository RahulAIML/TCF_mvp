"""20 concurrent mixed requests. /api/version must stay under a second the whole time.

    python qa/load_test.py http://127.0.0.1:8765 --seconds 300 --concurrency 20

Exits 1 if any version check is slower than --max-version-seconds (default 1)
or if the server stops answering.
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx

PATHS = [
    ("GET", "/api/version", None),
    ("GET", "/api/health", None),
    ("GET", "/healthz", None),
    ("POST", "/tcf/generate-listening-question", {"question_number": 2, "target_level": "A1", "defer_audio": True}),
    ("POST", "/tcf/generate-listening-audio", {"script": "Sophie : Bonjour à Montréal.\nMarc : Bonjour, le café est prêt.", "speakers": ["Sophie", "Marc"]}),
    ("POST", "/tcf/generate-question", {"question_number": 3, "target_level": "A1"}),
    ("POST", "/tcf/generate-writing-tasks", {}),
    ("GET", "/api/tts/voices?language=fr", None),
]


async def one(client: httpx.AsyncClient, method: str, path: str, body: dict | None) -> tuple[str, int, float]:
    started = time.perf_counter()
    try:
        response = await client.request(method, path, json=body, timeout=20)
        return path, response.status_code, time.perf_counter() - started
    except Exception:
        return path, 0, time.perf_counter() - started


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--max-version-seconds", type=float, default=1.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    slow: list[float] = []
    failures = 0
    version_samples = 0
    deadline = time.perf_counter() + args.seconds

    async with httpx.AsyncClient(base_url=base) as client:
        async def loop(index: int) -> None:
            nonlocal failures, version_samples
            n = 0
            while time.perf_counter() < deadline:
                # One slot always measures version. The others mix real endpoints.
                if index == 0 or n % 5 == 0:
                    path, status, elapsed = await one(client, "GET", "/api/version", None)
                    version_samples += 1
                    if status != 200 or elapsed > args.max_version_seconds:
                        slow.append(elapsed)
                        print(f"VERSION {status} {elapsed:.3f}s", flush=True)
                else:
                    method, path, body = PATHS[n % len(PATHS)]
                    _, status, elapsed = await one(client, method, path, body)
                    if status == 0 or elapsed > 30:
                        failures += 1
                        print(f"SLOW {method} {path} {status} {elapsed:.1f}s", flush=True)
                n += 1

        await asyncio.gather(*(loop(i) for i in range(args.concurrency)))

    print(f"version_samples={version_samples} slow_or_failed_version={len(slow)} other_failures={failures}")
    if slow:
        print(f"worst version {max(slow):.3f}s")
    return 1 if slow or version_samples == 0 else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
