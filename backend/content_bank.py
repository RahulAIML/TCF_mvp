"""Postgres (or SQLite in tests) seen-set and pre-generated pool.

Items are claimed with a single conditional UPDATE so two workers cannot take the same row.
The seen-set has no cap: a fingerprint is stored for the learner and the module, plus a simhash
when the text is long enough to compare paraphrases. Restarting the process does not forget either.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import content_dedupe as dedupe
from database import Base, SessionLocal, engine
from learner import active_learner

logger = logging.getLogger("tcf.content_bank")

_schema_lock = threading.Lock()
_schema_ready = False


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        import models  # noqa: F401  — register tables on Base
        Base.metadata.create_all(bind=engine)
        _schema_ready = True


def _session():
    ensure_schema()
    return SessionLocal()


def _dialect() -> str:
    bind = engine
    return bind.dialect.name if bind is not None else "sqlite"


# ── Seen items ──────────────────────────────────────────────────────────────

def is_seen(learner: str, module: str, fingerprint: str, simhash: str | None = None) -> bool:
    if not learner or not fingerprint:
        return False
    db = _session()
    try:
        exact = db.execute(
            text(
                "SELECT 1 FROM seen_items WHERE learner_key = :learner AND module = :module "
                "AND fingerprint = :fp LIMIT 1"
            ),
            {"learner": learner, "module": module, "fp": fingerprint},
        ).first()
        if exact:
            return True
        if not simhash:
            return False
        rows = db.execute(
            text(
                "SELECT simhash FROM seen_items WHERE learner_key = :learner AND module = :module "
                "AND simhash IS NOT NULL"
            ),
            {"learner": learner, "module": module},
        ).fetchall()
        return any(dedupe.near_duplicate(simhash, row[0]) for row in rows)
    finally:
        db.close()


def global_conflict(module: str, fingerprint: str, simhash: str | None = None) -> bool:
    db = _session()
    try:
        exact = db.execute(
            text("SELECT 1 FROM content_registry WHERE fingerprint = :fp LIMIT 1"),
            {"fp": fingerprint},
        ).first()
        if exact:
            return True
        if not simhash:
            return False
        rows = db.execute(
            text("SELECT simhash FROM content_registry WHERE module = :module AND simhash IS NOT NULL"),
            {"module": module},
        ).fetchall()
        return any(dedupe.near_duplicate(simhash, row[0]) for row in rows)
    finally:
        db.close()


def remember(
    learner: str,
    module: str,
    fingerprint: str,
    simhash: str | None = None,
    label: str | None = None,
) -> None:
    """Record that this learner was served this item. A second insert of the same fingerprint is ignored."""
    if not learner or not fingerprint:
        return
    db = _session()
    try:
        db.execute(
            text(
                "INSERT INTO seen_items (learner_key, module, fingerprint, simhash, label, created_at) "
                "VALUES (:learner, :module, :fp, :sim, :label, :now)"
            ),
            {
                "learner": learner,
                "module": module,
                "fp": fingerprint,
                "sim": simhash,
                "label": (label or "")[:240] or None,
                "now": datetime.utcnow(),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception:
        db.rollback()
        logger.exception("Could not record seen item")
        raise
    finally:
        db.close()
    _register_global(module, fingerprint, simhash)


def _register_global(module: str, fingerprint: str, simhash: str | None) -> None:
    db = _session()
    try:
        db.execute(
            text(
                "INSERT INTO content_registry (fingerprint, module, simhash, created_at) "
                "VALUES (:fp, :module, :sim, :now)"
            ),
            {"fp": fingerprint, "module": module, "sim": simhash, "now": datetime.utcnow()},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


def recent_labels(learner: str, module: str, limit: int = 30) -> list[str]:
    db = _session()
    try:
        rows = db.execute(
            text(
                "SELECT label FROM seen_items WHERE learner_key = :learner AND module = :module "
                "AND label IS NOT NULL ORDER BY id DESC LIMIT :limit"
            ),
            {"learner": learner, "module": module, "limit": limit},
        ).fetchall()
        return [row[0] for row in rows if row[0]]
    finally:
        db.close()


def remember_text(module: str, text: str, learner: str | None = None, label: str | None = None) -> str:
    learner = learner or active_learner()
    fp = dedupe.fingerprint(text)
    remember(learner, module, fp, dedupe.simhash_of(text), label or text[:240])
    return fp


def text_seen(module: str, text: str, learner: str | None = None) -> bool:
    learner = learner or active_learner()
    return is_seen(learner, module, dedupe.fingerprint(text), dedupe.simhash_of(text))


# ── Exam slots (same question when a learner resumes the same exam) ────────

def load_exam(learner: str, exam_session_id: str, module: str, slot: str) -> dict | None:
    db = _session()
    try:
        row = db.execute(
            text(
                "SELECT payload FROM exam_slots WHERE learner_key = :learner AND exam_session_id = :sid "
                "AND module = :module AND slot = :slot"
            ),
            {"learner": learner, "sid": exam_session_id, "module": module, "slot": slot},
        ).first()
        if not row:
            return None
        return json.loads(row[0])
    finally:
        db.close()


def save_exam(learner: str, exam_session_id: str, module: str, slot: str, fingerprint: str, payload: dict) -> None:
    db = _session()
    try:
        db.execute(
            text(
                "INSERT INTO exam_slots (learner_key, exam_session_id, module, slot, fingerprint, payload, created_at) "
                "VALUES (:learner, :sid, :module, :slot, :fp, :payload, :now)"
            ),
            {
                "learner": learner,
                "sid": exam_session_id,
                "module": module,
                "slot": slot,
                "fp": fingerprint,
                "payload": json.dumps(payload, ensure_ascii=False),
                "now": datetime.utcnow(),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


# ── Writing evaluation cache (identical text → identical scores) ───────────

def writing_eval_key(task_type: str, prompt_text: str, response_text: str) -> str:
    blob = "\n".join((task_type or "", dedupe.normalize_text(prompt_text), dedupe.normalize_text(response_text)))
    return dedupe.fingerprint(blob)


def get_writing_eval(cache_key: str) -> dict | None:
    db = _session()
    try:
        row = db.execute(
            text("SELECT raw_text, result_json FROM writing_eval_cache WHERE cache_key = :key"),
            {"key": cache_key},
        ).first()
        if not row:
            return None
        return {"raw_text": row[0], "result": json.loads(row[1])}
    finally:
        db.close()


def put_writing_eval(cache_key: str, raw_text: str, result: dict) -> None:
    db = _session()
    try:
        db.execute(
            text(
                "INSERT INTO writing_eval_cache (cache_key, raw_text, result_json, created_at) "
                "VALUES (:key, :raw, :result, :now)"
            ),
            {"key": cache_key, "raw": raw_text, "result": json.dumps(result, ensure_ascii=False), "now": datetime.utcnow()},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    finally:
        db.close()


# ── Pool ────────────────────────────────────────────────────────────────────

def pool_ready_counts(pool: str) -> dict[str, int]:
    db = _session()
    try:
        rows = db.execute(
            text(
                "SELECT pool_key, COUNT(*) FROM pregen_items "
                "WHERE pool = :pool AND claimed_at IS NULL GROUP BY pool_key"
            ),
            {"pool": pool},
        ).fetchall()
        return {row[0]: int(row[1]) for row in rows}
    finally:
        db.close()


def insert_item(pool: str, pool_key: str, module: str, fingerprint: str, simhash: str | None, payload: Any) -> bool:
    """Insert one unclaimed item. Returns False when the fingerprint (or a near copy) is already known."""
    if global_conflict(module, fingerprint, simhash):
        return False
    db = _session()
    try:
        existing = db.execute(
            text("SELECT 1 FROM pregen_items WHERE pool = :pool AND fingerprint = :fp LIMIT 1"),
            {"pool": pool, "fp": fingerprint},
        ).first()
        if existing:
            return False
        db.execute(
            text(
                "INSERT INTO pregen_items (pool, pool_key, fingerprint, simhash, payload, created_at) "
                "VALUES (:pool, :key, :fp, :sim, :payload, :now)"
            ),
            {
                "pool": pool,
                "key": pool_key,
                "fp": fingerprint,
                "sim": simhash,
                "payload": json.dumps(payload, ensure_ascii=False),
                "now": datetime.utcnow(),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    finally:
        db.close()
    _register_global(module, fingerprint, simhash)
    return True


def _acceptable(learner: str | None, module: str, fingerprint: str, simhash: str | None) -> bool:
    if not learner:
        return True
    return not is_seen(learner, module, fingerprint, simhash)


_sqlite_claim_lock = threading.Lock()


def claim_for(pool: str, pool_key: str, module: str, learner: str | None, attempts: int = 12) -> dict | None:
    """Atomically claim one unclaimed row this learner has not already been served.

    Postgres uses SELECT ... FOR UPDATE SKIP LOCKED inside the statement. SQLite has no skip-locked,
    so claims in this process take a short lock and the UPDATE still requires claimed_at IS NULL.
    """
    from sqlalchemy.exc import OperationalError
    lock = _sqlite_claim_lock if _dialect() == "sqlite" else nullcontext()
    for _try in range(5):
        try:
            with lock:
                return _claim_once(pool, pool_key, module, learner, attempts)
        except OperationalError:
            if _try == 4:
                logger.warning("Pool claim lock timed out for %s/%s", pool, pool_key)
                return None
            import time
            time.sleep(0.05 * (_try + 1))
    return None


def _claim_once(pool: str, pool_key: str, module: str, learner: str | None, attempts: int) -> dict | None:
    from sqlalchemy.exc import OperationalError
    db = _session()
    try:
        if _dialect() == "postgresql":
            rows = db.execute(
                text(
                    "SELECT id, payload, fingerprint, simhash FROM pregen_items "
                    "WHERE pool = :pool AND pool_key = :key AND claimed_at IS NULL "
                    "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT :limit"
                ),
                {"pool": pool, "key": pool_key, "limit": attempts},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id, payload, fingerprint, simhash FROM pregen_items "
                    "WHERE pool = :pool AND pool_key = :key AND claimed_at IS NULL "
                    "ORDER BY id LIMIT :limit"
                ),
                {"pool": pool, "key": pool_key, "limit": attempts},
            ).fetchall()
        chosen = None
        for row in rows:
            if _acceptable(learner, module, row[2], row[3]):
                chosen = row
                break
        if chosen is None:
            db.rollback()
            return None
        token = uuid.uuid4().hex
        updated = db.execute(
            text(
                "UPDATE pregen_items SET claimed_at = :now, claim_token = :token "
                "WHERE id = :id AND claimed_at IS NULL"
            ),
            {"id": chosen[0], "token": token, "now": datetime.utcnow()},
        )
        if updated.rowcount != 1:
            db.rollback()
            return None
        db.commit()
        return {"payload": json.loads(chosen[1]), "fingerprint": chosen[2], "simhash": chosen[3]}
    except OperationalError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Pool claim failed for %s/%s", pool, pool_key)
        return None
    finally:
        db.close()


class DurablePool:
    """Background filler with the same take/fill/stats shape as the old in-memory pool.

    `take` claims a database row. `fill` generates until `target` unclaimed rows exist for the key.
    """

    def __init__(
        self,
        name: str,
        producer: Callable[[Any], Any],
        target: int,
        warm_keys: tuple = (),
        module: str = "item",
        fingerprint_of: Callable[[Any], str] | None = None,
        simhash_of: Callable[[Any], str | None] | None = None,
        dump: Callable[[Any], Any] | None = None,
        load: Callable[[Any], Any] | None = None,
    ) -> None:
        import pregen_pool
        self.name = name
        self._producer = producer
        self._target = max(0, target)
        self.warm_keys = warm_keys
        self.module = module
        self._fingerprint_of = fingerprint_of or (lambda item: dedupe.fingerprint(json.dumps(item, sort_keys=True, default=str)))
        self._simhash_of = simhash_of or (lambda item: None)
        self._dump = dump or _default_dump
        self._load = load or (lambda payload: payload)
        self._lock = threading.Lock()
        self._in_flight: dict[str, int] = {}
        self._failures: dict[str, int] = {}
        pregen_pool._REGISTRY.append(self)

    def take(self, key: Any) -> Any:
        claimed = claim_for(self.name, str(key), self.module, active_learner())
        if claimed is None:
            return None
        return self._load(claimed["payload"])

    def fill(self, key: Any) -> None:
        import os
        import pregen_pool
        if not pregen_pool._ENABLED or self._target == 0:
            return
        key_s = str(key)
        with self._lock:
            ready = pool_ready_counts(self.name).get(key_s, 0)
            in_flight = self._in_flight.get(key_s, 0)
            if self._failures.get(key_s, 0) >= 3:
                return
            missing = self._target - ready - in_flight
            if missing <= 0:
                return
            self._in_flight[key_s] = in_flight + missing
        for submitted in range(missing):
            try:
                pregen_pool._EXECUTOR.submit(self._produce, key)
            except RuntimeError:
                with self._lock:
                    self._in_flight[key_s] = max(0, self._in_flight.get(key_s, 0) - (missing - submitted))
                return

    def _produce(self, key: Any) -> None:
        key_s = str(key)
        try:
            item = None
            for _ in range(3):
                item = self._producer(key)
                payload = self._dump(item)
                fp = self._fingerprint_of(item)
                sim = self._simhash_of(item)
                if insert_item(self.name, key_s, self.module, fp, sim, payload):
                    item = True
                    break
                item = None
            if item is None:
                raise RuntimeError("generated item was already known")
            with self._lock:
                self._failures[key_s] = 0
        except Exception as error:
            logger.warning("Durable pool %s[%s] failed: %s", self.name, key_s, error)
            with self._lock:
                failures = self._failures.get(key_s, 0) + 1
                self._failures[key_s] = failures
            if failures == 3:
                timer = threading.Timer(120, self._reset_failures, args=(key_s,))
                timer.daemon = True
                timer.start()
        finally:
            with self._lock:
                self._in_flight[key_s] = max(0, self._in_flight.get(key_s, 0) - 1)

    def _reset_failures(self, key: str) -> None:
        with self._lock:
            self._failures[key] = 0
        self.fill(key)

    def stats(self) -> dict[str, dict[str, int]]:
        ready = pool_ready_counts(self.name)
        with self._lock:
            keys = set(ready) | set(self._in_flight)
            return {
                k: {"ready": ready.get(k, 0), "in_flight": self._in_flight.get(k, 0)}
                for k in keys
            }


def _default_dump(item: Any) -> Any:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item
