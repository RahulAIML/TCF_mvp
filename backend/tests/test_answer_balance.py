from collections import Counter

import answer_balance


def test_every_block_of_four_uses_each_letter_once():
    letters = [answer_balance.next_letter("t:block") for _ in range(400)]
    for i in range(0, 400, 4):
        assert sorted(letters[i:i + 4]) == ["A", "B", "C", "D"]


def test_buckets_are_independent_and_balanced():
    counts = Counter(answer_balance.next_letter("t:x") for _ in range(100))
    assert counts == Counter({"A": 25, "B": 25, "C": 25, "D": 25})
    assert answer_balance.next_letter("t:y") in "ABCD"


def test_order_is_not_fixed():
    seqs = {tuple(answer_balance.next_letter("t:order") for _ in range(4)) for _ in range(50)}
    assert len(seqs) > 1
