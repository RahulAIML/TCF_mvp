"""Durable seen-set and pool: one learner never receives the same item again, including after a restart."""
import itertools
import threading

import pytest

import content_bank
import content_dedupe as dedupe
import listening_service as ls
import reading_service as rs
from learner import push_learner


def test_fingerprint_strips_articles_and_accents():
    assert dedupe.normalize_vocab("Le château") == dedupe.normalize_vocab("chateau")
    assert dedupe.vocab_fingerprint("les chats") == dedupe.vocab_fingerprint("chats")
    assert dedupe.fingerprint("Bonjour, le monde.") == dedupe.fingerprint("bonjour le monde")


def test_simhash_flags_a_light_paraphrase_and_ignores_short_text():
    base = " ".join(f"mot{i}" for i in range(40))
    changed = base.replace("mot3", "mot3")
    assert dedupe.simhash_of("le chat") is None
    assert dedupe.near_duplicate(dedupe.simhash_of(base), dedupe.simhash_of(changed))
    other = " ".join(f"autre{i}" for i in range(40))
    assert not dedupe.near_duplicate(dedupe.simhash_of(base), dedupe.simhash_of(other))


def test_seen_set_has_no_cap_and_survives_a_new_lookup():
    learner = "guest:seen-set-durable"
    for i in range(30):
        content_bank.remember(learner, "reading", f"{i:064x}", None, label=f"item {i}")
    assert content_bank.is_seen(learner, "reading", f"{0:064x}")
    assert content_bank.is_seen(learner, "reading", f"{29:064x}")
    assert not content_bank.is_seen(learner, "reading", f"{99:064x}")
    assert "item 29" in content_bank.recent_labels(learner, "reading", 5)


def test_pool_claim_is_exclusive_under_concurrency():
    for i in range(12):
        assert content_bank.insert_item("claim_test", "B1", "claim_test", f"c{i:04d}".ljust(64, "a"), None, {"n": i})
    found = []
    lock = threading.Lock()

    def grab():
        for _ in range(4):
            row = content_bank.claim_for("claim_test", "B1", "claim_test", None)
            if row is None:
                return
            with lock:
                found.append(row["payload"]["n"])

    threads = [threading.Thread(target=grab) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(found) == 12
    assert len(set(found)) == 12
    assert content_bank.claim_for("claim_test", "B1", "claim_test", None) is None


def test_claimed_item_is_not_served_again_after_memory_is_cleared(monkeypatch):
    """Simulates a restart: the in-memory registry is empty, the database is not."""
    learner = "guest:restart-reading-1"
    fixed = {
        "text": " ".join(f"uniquephrase{i}" for i in range(80)),
        "question": "Que dit le document ?",
        "options": ["alpha", "beta", "gamma", "delta"],
        "correct_answer": "A",
        "explanation": "Le texte le dit clairement.",
        "topic": "phrase unique",
    }

    def always_same(prompt, temperature):
        return dict(fixed)

    monkeypatch.setattr(rs, "_llm_json", always_same)
    monkeypatch.setattr(rs._READING_POOL, "take", lambda key: None)
    monkeypatch.setattr(rs, "_registry", rs.UniquenessRegistry())
    monkeypatch.setattr(rs, "_served", rs.SessionServed())
    with push_learner(learner):
        first = rs.get_reading_question(12, session_id="restart-reading-1", target_level="B1")
        rs._registry = rs.UniquenessRegistry()
        rs._served = rs.SessionServed()
        rs._exam_cache.clear()
        with pytest.raises(RuntimeError):
            rs.get_reading_question(12, session_id="restart-reading-1", target_level="B1")
    assert "uniquephrase0" in first.text


def test_two_guest_ids_do_not_share_a_seen_set(client, monkeypatch):
    seq = itertools.count()

    def fake_question(number, session_id=None, defer_audio=True, target_level=None):
        n = next(seq)
        return ls.ListeningQuestionResponse(
            question_id=f"q{n}", level="B1", script=f"script {n} " + "mot " * 5,
            question=f"Question {n} ?", options=["A. a", "B. b", "C. c", "D. d"],
            correct_answer="A", explanation="parce que",
        )

    monkeypatch.setattr(ls, "get_question", fake_question)
    one = client.post("/tcf/generate-listening-question", json={"question_number": 12, "target_level": "B1"},
                      headers={"X-Learner-Id": "guest-one-1111"})
    two = client.post("/tcf/generate-listening-question", json={"question_number": 12, "target_level": "B1"},
                      headers={"X-Learner-Id": "guest-two-2222"})
    assert one.status_code == 200 and two.status_code == 200
    assert one.json()["question_id"] != two.json()["question_id"]


def test_listening_does_not_repeat_a_question_for_one_learner(monkeypatch):
    made = itertools.count()

    def build(level, question_number=None, with_audio=True):
        n = next(made)
        # After the first serve the generator keeps offering the same id, which must be refused.
        qid = "same" if n < 3 else f"fresh-{n}"
        return ls.ListeningQuestionResponse(
            question_id=qid, level=level, script=f"script {qid}", question=f"Q {qid}",
            options=["A. a", "B. b", "C. c", "D. d"], correct_answer="B", explanation="ok",
        )

    monkeypatch.setattr(ls, "POOL", type("P", (), {"take": lambda self, key: None})())
    monkeypatch.setattr(ls, "build_question", build)
    monkeypatch.setattr(ls, "HISTORY", ls._History())
    with push_learner("guest:listen-once-1111"):
        first = ls.get_question(15, session_id="listen-once-1111", target_level="B1")
        second = ls.get_question(15, session_id="listen-once-1111", target_level="B1")
    assert first.question_id == "same"
    assert second.question_id != first.question_id


def test_pronunciation_fallback_is_tracked(client):
    headers = {"X-Learner-Id": "pron-learner-1111"}
    first = client.post("/api/pronunciation/prompts", json={"language": "fr", "level": "A1", "count": 4}, headers=headers)
    second = client.post("/api/pronunciation/prompts", json={"language": "fr", "level": "A1", "count": 4}, headers=headers)
    assert first.status_code == 200 and second.status_code == 200, first.text
    a = {item["text"] for item in first.json()["prompts"]}
    b = {item["text"] for item in second.json()["prompts"]}
    assert a and not (a & b)


def test_vocabulary_words_are_not_repeated_for_the_learner(client, monkeypatch):
    import speaking_pregen
    counter = itertools.count()

    def fake_generate_vocabulary(level="A2", count=5, topic=None, language="fr", exclude=None):
        excluded = {w.lower() for w in (exclude or [])}
        out = []
        while len(out) < count:
            word = f"mot{next(counter)}"
            if word not in excluded:
                out.append({"word": word, "meaning": "m", "example": "e", "example_translation": None, "phonetic": None})
        return out

    monkeypatch.setattr(speaking_pregen.gemini_service, "generate_vocabulary", fake_generate_vocabulary)
    monkeypatch.setattr(speaking_pregen.vocab_pool, "take", lambda key: None)
    monkeypatch.setattr("routers.pronunciation_routes._warm_guides", lambda words, language: None)
    headers = {"X-Learner-Id": "vocab-learner-1111"}
    body = {"level": "A2", "count": 4, "session_id": "vocab-learner-1111"}
    first = client.post("/api/pronunciation/vocabulary/generate", json=body, headers=headers)
    second = client.post("/api/pronunciation/vocabulary/generate", json=body, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    words = [w["word"] for w in first.json()["words"] + second.json()["words"]]
    assert len(words) == len(set(words)) == 8
