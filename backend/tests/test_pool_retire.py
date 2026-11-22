import json
import uuid

import pytest
from sqlalchemy import text

import content_bank
import pool_retire


def _item(question, options, correct="B", level="C2", **extra):
    return {
        "level": level,
        "script": "Marc : Cette décision change l'équilibre du quartier. Sophie : Elle ignore pourtant les commerçants.",
        "text": "Un article sur la vie du quartier et sur ses commerces locaux.",
        "question": question,
        "options": [f"{letter}. {body}" for letter, body in zip("ABCD", options)],
        "correct_answer": correct,
        "explanation": "Le locuteur nuance son propos en reconnaissant un avantage avant de formuler une réserve.",
        **extra,
    }


EVEN = [
    "Il salue l'intention mais regrette un calendrier trop serré.",
    "Il approuve le fond tout en doutant des moyens prévus.",
    "Il reconnaît l'utilité du projet mais redoute son coût final.",
    "Il admet l'urgence mais conteste la méthode retenue ici.",
]
LONG_RIGHT = [
    "Il approuve.",
    "Il refuse.",
    "Il doute des délais annoncés par la mairie.",
    "Il tourne en dérision un dispositif précaire dont l'habillage moderne masque l'incapacité complète de l'État à offrir des soins dignes aux familles.",
]


@pytest.fixture()
def pool_rows(app):
    content_bank.ensure_schema()

    def clean():
        with content_bank.engine.begin() as conn:
            conn.execute(text("DELETE FROM pregen_items"))

    clean()
    yield
    clean()


def _insert(pool, key, label, payload):
    # The seen-fingerprint registry outlives a test, so every insert gets a fresh fingerprint.
    assert content_bank.insert_item(pool, key, "test", f"{label}~{uuid.uuid4().hex[:10]}", None, payload)


def _state():
    with content_bank.engine.begin() as conn:
        rows = conn.execute(text("SELECT fingerprint, claimed_at, claim_token, payload FROM pregen_items")).fetchall()
    return {r[0].split("~")[0]: r for r in rows}


def test_only_failing_unused_questions_are_retired(pool_rows):
    _insert("reading_question", "C2", "good", _item("Que laisse entendre le chroniqueur ?", EVEN))
    _insert("reading_question", "C2", "banned", _item("Quelle est la position réelle de l'auteur ?", EVEN))
    _insert("reading_question", "C2", "longest", _item("Que dénonce l'auteur ?", LONG_RIGHT, correct="D"))
    _insert("listening", "C2", "banned-listening", _item("Quelle est la position réelle du narrateur ?", EVEN))
    _insert("writing_tasks", "all", "other-pool", _item("Quelle est la position réelle de l'auteur ?", EVEN))
    _insert("reading_question", "C2", "already-used", _item("Quelle est la position réelle de l'auteur ?", EVEN))
    with content_bank.engine.begin() as conn:
        conn.execute(text("UPDATE pregen_items SET claimed_at = CURRENT_TIMESTAMP WHERE fingerprint LIKE 'already-used~%'"))

    result = pool_retire.retire_stale_items()

    state = _state()
    assert result["retired"] == 3 and result["scanned"] == 4
    assert state["good"][1] is None
    for fp in ("banned", "longest", "banned-listening"):
        assert state[fp][1] is not None and state[fp][2] == pool_retire.RETIRED_TOKEN
    assert state["other-pool"][1] is None, "other pools are never touched"
    assert state["already-used"][2] != pool_retire.RETIRED_TOKEN, "rows already served keep their own history"
    assert len(state) == 6, "nothing is deleted"
    assert json.loads(state["banned"][3])["question"].startswith("Quelle est la position réelle")


def test_second_run_changes_nothing_and_retired_rows_can_be_restored(pool_rows):
    _insert("reading_question", "C2", "banned", _item("Quelle est la position réelle de l'auteur ?", EVEN))
    assert pool_retire.retire_stale_items()["retired"] == 1
    assert pool_retire.retire_stale_items() == {"scanned": 0, "retired": 0}

    with content_bank.engine.begin() as conn:
        conn.execute(text("UPDATE pregen_items SET claimed_at = NULL, claim_token = NULL WHERE fingerprint LIKE 'banned~%'"))
    assert _state()["banned"][1] is None


def test_retired_questions_are_never_served(pool_rows):
    _insert("reading_question", "C2", "banned", _item("Quelle est la position réelle de l'auteur ?", EVEN))
    pool_retire.retire_stale_items()
    assert content_bank.claim_for("reading_question", "C2", "reading", "learner-x") is None
