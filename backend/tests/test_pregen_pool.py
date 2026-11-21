import itertools
import threading
import time

import pregen_pool
from pregen_pool import PregenPool


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_fills_to_target_and_serves_each_item_once():
    counter = itertools.count()
    pool = PregenPool("t_once", lambda key: f"{key}-{next(counter)}", target=4)
    assert pool.take("B2") is None
    assert _wait_for(lambda: pool.stats().get("B2", {}).get("ready") == 4)

    served = [pool.take("B2") for _ in range(4)]
    assert None not in served
    assert len(set(served)) == 4, "an item was handed out twice"
    assert _wait_for(lambda: pool.stats()["B2"]["ready"] == 4), "pool did not refill after draining"


def test_keys_are_isolated():
    pool = PregenPool("t_keys", lambda key: key, target=2)
    pool.fill("A1")
    pool.fill("C2")
    assert _wait_for(lambda: pool.stats().get("A1", {}).get("ready") == 2 and pool.stats().get("C2", {}).get("ready") == 2)
    assert pool.take("A1") == "A1"
    assert pool.take("C2") == "C2"


def test_concurrent_takes_never_duplicate():
    counter = itertools.count()
    lock = threading.Lock()

    def producer(key):
        with lock:
            return next(counter)

    pool = PregenPool("t_concurrent", producer, target=20)
    pool.fill("k")
    assert _wait_for(lambda: pool.stats()["k"]["ready"] == 20)
    results = []
    res_lock = threading.Lock()

    def worker():
        item = pool.take("k")
        with res_lock:
            results.append(item)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    got = [r for r in results if r is not None]
    assert len(got) == len(set(got))


def test_failing_producer_backs_off_and_take_returns_none():
    calls = []

    def producer(key):
        calls.append(key)
        raise RuntimeError("provider down")

    pool = PregenPool("t_fail", producer, target=3)
    pool.fill("x")
    assert _wait_for(lambda: len(calls) >= 3)
    time.sleep(0.2)
    before = len(calls)
    assert pool.take("x") is None
    time.sleep(0.2)
    assert len(calls) == before, "pool kept hammering a failing provider"


def test_expired_items_are_discarded():
    pool = PregenPool("t_age", lambda key: "old", target=1, max_age_seconds=0.05)
    pool.fill("k")
    assert _wait_for(lambda: pool.stats()["k"]["ready"] == 1)
    time.sleep(0.1)
    assert pool.take("k") is None


def test_warm_all_fills_registered_warm_keys():
    pool = PregenPool("t_warm", lambda key: key, target=1, warm_keys=("B1",))
    pregen_pool.warm_all()
    assert _wait_for(lambda: pool.stats().get("B1", {}).get("ready") == 1)
    assert "t_warm" in pregen_pool.all_stats()
