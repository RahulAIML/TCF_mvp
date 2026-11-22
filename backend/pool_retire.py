"""Retire stored listening/reading questions that fail the current quality checks.

Questions generated before the tone, length and wording guards existed are still waiting in the durable pool
(`pregen_items`). This marks the failing ones as used so nobody is served them. Nothing is deleted: a retired row
keeps its payload, and setting `claimed_at` and `claim_token` back to NULL restores it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text

import answer_quality
import content_bank
import quality_guard

logger = logging.getLogger("tcf.pool_retire")

RETIRED_TOKEN = "retired:quality"
BATCH = 100
POOLS = ("listening", "reading_question")
_OPTION_PREFIX = re.compile(r"^\s*[A-D][\.\)]\s*")


def _problem_for(pool: str, level: str, payload: dict[str, Any]) -> Optional[str]:
    question = str(payload.get("question", ""))
    options = payload.get("options") or []
    letter = str(payload.get("correct_answer", "")).strip().upper()[:1]
    if len(options) != 4 or letter not in "ABCD" or not question:
        return "malformed item"
    stem = answer_quality.StemHistory(window=0).problem("retire", question)
    if stem:
        return stem
    if level not in answer_quality.CHECKED_LEVELS:
        return None
    cleaned = [_OPTION_PREFIX.sub("", str(o)).strip() for o in options]
    index = "ABCD".index(letter)
    length = answer_quality.option_problem(level, question, cleaned, index, None)
    if length:
        return length
    body = str(payload.get("script") or payload.get("text") or "")
    problems = quality_guard.item_problems(
        level, options, letter, str(payload.get("explanation", "")), body, question
    )
    return "; ".join(problems) if problems else None


def retire_stale_items(max_rows: int = 5000) -> dict[str, int]:
    """Scan unused rows in id order, in small batches. Returns {'scanned': n, 'retired': n}."""
    scanned = retired = 0
    last_id = 0
    session = content_bank._session()
    try:
        while scanned < max_rows:
            rows = session.execute(
                text(
                    "SELECT id, pool, pool_key, payload FROM pregen_items "
                    "WHERE claimed_at IS NULL AND pool IN (:a, :b) AND id > :last "
                    "ORDER BY id LIMIT :n"
                ),
                {"a": POOLS[0], "b": POOLS[1], "last": last_id, "n": BATCH},
            ).fetchall()
            if not rows:
                break
            for row in rows:
                last_id = max(last_id, int(row[0]))
                scanned += 1
                try:
                    reason = _problem_for(str(row[1]), str(row[2]).upper(), json.loads(row[3]))
                except Exception as error:  # noqa: BLE001 - an unreadable row is left alone
                    logger.warning("Pool row %s could not be checked: %s", row[0], error)
                    continue
                if not reason:
                    continue
                done = session.execute(
                    text(
                        "UPDATE pregen_items SET claimed_at = :now, claim_token = :token "
                        "WHERE id = :id AND claimed_at IS NULL"
                    ),
                    {"id": row[0], "now": datetime.utcnow(), "token": RETIRED_TOKEN},
                )
                retired += int(done.rowcount or 0)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("Retiring stale pool items failed")
    finally:
        session.close()
    logger.info("Pool cleanup: scanned %s unused items, retired %s", scanned, retired)
    return {"scanned": scanned, "retired": retired}


def run_in_background(delay_seconds: float = 20.0) -> None:
    """Off by setting RETIRE_STALE_POOL_ITEMS=0. Runs once, after the app is already answering requests."""
    if os.getenv("RETIRE_STALE_POOL_ITEMS", "1") == "0":
        return

    def _run() -> None:
        import time
        time.sleep(delay_seconds)
        retire_stale_items()

    threading.Thread(target=_run, name="pool-retire", daemon=True).start()
