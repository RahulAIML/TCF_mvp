"""Balanced answer positions: every run of four questions per bucket uses A, B, C and D once, in random order."""
import random
import threading
from typing import Dict, List

LETTERS = ("A", "B", "C", "D")
_lock = threading.Lock()
_bags: Dict[str, List[str]] = {}


def next_letter(bucket: str) -> str:
    with _lock:
        bag = _bags.get(bucket)
        if not bag:
            bag = list(LETTERS)
            random.shuffle(bag)
            _bags[bucket] = bag
        return bag.pop()
