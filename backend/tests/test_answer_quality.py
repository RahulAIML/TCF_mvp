import itertools
import random
import re
from collections import Counter

import pytest

import answer_balance
import answer_quality as aq
import listening_service as ls
import reading_service as rs
import tcf_ai_service

_ids = itertools.count()


# ── Length check ─────────────────────────────────────────────────────────────

def test_much_longer_correct_option_is_rejected():
    options = ["Il critique le projet", "Il approuve le projet", "Il ignore le projet",
               "Il regrette que le projet néglige les familles modestes du quartier"]
    assert aq.length_problem(options, 3)


def test_much_shorter_correct_option_is_rejected():
    options = ["Il approuve sans réserve le nouveau projet", "Il refuse catégoriquement toute la réforme",
               "Il s'interroge longuement sur le calendrier", "Il doute"]
    assert aq.length_problem(options, 3)


def test_comparable_lengths_pass():
    options = ["Il critique le calendrier", "Il critique le coût total", "Il critique les horaires",
               "Il critique la méthode"]
    for i in range(4):
        assert aq.length_problem(options, i) is None


def test_length_and_blind_checks_skip_a1_a2():
    lopsided = ["9 h", "10 h", "11 h", "à midi et demi précisément selon l'annonce"]
    assert aq.option_problem("A2", "Quand ?", lopsided, 3, lambda p, t: {"guess": "D", "confidence": 1}) is None
    assert aq.option_problem("B1", "Quand ?", lopsided, 3, None)


# ── Blind guess ──────────────────────────────────────────────────────────────

def test_confident_blind_guess_of_the_right_answer_is_rejected():
    llm = lambda p, t: {"guess": "C", "confidence": 0.8}  # noqa: E731
    assert aq.blind_problem(llm, "Q ?", ["a", "b", "c", "d"], 2)


@pytest.mark.parametrize("reply", [
    {"guess": "C", "confidence": 0.3},   # right but unsure: chance level
    {"guess": "A", "confidence": 0.95},  # confident but wrong
    {},                                  # unusable reply
    {"guess": "Z", "confidence": 0.9},
])
def test_unconfident_wrong_or_unusable_guesses_pass(reply):
    assert aq.blind_problem(lambda p, t: reply, "Q ?", ["a", "b", "c", "d"], 2) is None


def test_blind_check_failure_never_blocks_generation():
    def broken(prompt, temperature):
        raise RuntimeError("model down")
    assert aq.blind_problem(broken, "Q ?", ["a", "b", "c", "d"], 0) is None


def test_blind_prompt_never_contains_the_document():
    seen = []
    aq.blind_guess(lambda p, t: seen.append(p) or {}, "Que reproche Lucie ?", ["w", "x", "y", "z"])
    assert "Que reproche Lucie ?" in seen[0] and "A. w" in seen[0] and "D. z" in seen[0]


def test_batch_blind_flags():
    items = [("q1", ["a", "b", "c", "d"], 0), ("q2", ["a", "b", "c", "d"], 1), ("q3", ["a", "b", "c", "d"], 2)]
    reply = {"guesses": [{"guess": "A", "confidence": 0.9}, {"guess": "A", "confidence": 0.9},
                         {"guess": "C", "confidence": 0.2}]}
    assert aq.batch_blind_flags(lambda p, t: reply, items) == [True, False, False]
    assert aq.batch_blind_flags(lambda p, t: {}, items) == [False, False, False]


# ── Stems and focus ──────────────────────────────────────────────────────────

def test_recent_question_opening_is_rejected_and_window_rolls():
    stems = aq.StemHistory(window=2)
    stems.record("b", "Que reproche Lucie au nouveau règlement ?")
    assert stems.problem("b", "Que reproche Lucie au nouveau règlement municipal ?")
    assert stems.problem("b", "Pourquoi Lucie hésite-t-elle ?") is None
    stems.record("b", "Pourquoi Lucie hésite-t-elle ?")
    stems.record("b", "Quel effet produit l'exemple cité ?")
    assert stems.problem("b", "Que reproche Lucie au nouveau règlement ?") is None
    assert stems.problem("other", "Pourquoi Lucie hésite-t-elle ?") is None


@pytest.mark.parametrize("window", [0, 30])
def test_position_reelle_is_always_banned(window):
    stems = aq.StemHistory(window=window)
    assert stems.problem("b", "Quelle est la position réelle de la chroniqueuse ?")
    assert stems.problem("b", "Quelle est la POSITION REELLE de l'auteur ?")


def test_focus_rotation_uses_every_type_before_repeating():
    for level, focuses in aq.QUESTION_FOCUS.items():
        drawn = [aq.next_focus(f"t:{level}", level) for _ in range(len(focuses))]
        assert sorted(drawn) == sorted(focuses)


def test_prompts_carry_focus_option_rules_and_no_position_reelle():
    prompt = ls._build_prompt("C2", 37, "une chronique radio argumentée ou ironique", False, ("Lucie", "Hugo"), "B",
                              [], "le reproche formulé", ["que reproche lucie au"])
    assert "le reproche formulé" in prompt and "que reproche lucie au" in prompt
    assert "au moins DEUX distracteurs" in prompt
    assert "position réelle" not in prompt.replace("N'utilise jamais l'expression « position réelle »", "")
    rprompt = rs.build_reading_prompt("C2", 38, "C", [], "un sous-entendu", [], ("Lucie", "Hugo"))
    assert "un sous-entendu" in rprompt and "au moins DEUX distracteurs" in rprompt and "Lucie" in rprompt
    assert "position réelle de l" not in rs.READING_SPECS["C2"]["focus"]


# ── Names ────────────────────────────────────────────────────────────────────

def test_name_pool_is_large_and_gendered():
    assert len(aq.MALE_NAMES) + len(aq.FEMALE_NAMES) >= 80
    assert len(set(aq.MALE_NAMES)) == len(aq.MALE_NAMES) and len(set(aq.FEMALE_NAMES)) == len(aq.FEMALE_NAMES)
    assert not set(aq.MALE_NAMES) & set(aq.FEMALE_NAMES)
    for name in aq.MALE_NAMES + aq.FEMALE_NAMES:
        assert ls.SPEAKER_LABEL_RE.match(f"{name} : Bonjour."), name  # every name is detectable as a speaker
    assert ls._NAME_GENDER["Lucie"] == "female" and ls._NAME_GENDER["Hugo"] == "male"


def test_no_name_repeats_within_the_rotation_window():
    rotation = aq.NameRotation(window=40)
    picked = []
    for _ in range(20):
        a, b = rotation.pair()
        assert a != b
        picked += [a, b]
    assert len(picked) == len(set(picked)) == 40


# ── Generators reject guessable items and keep the letter rotation ──────────

def _listening_payload(level, target):
    lo, hi = ls.LISTENING_SPECS[level]["words"]
    n = next(_ids)
    rng = random.Random(n)
    vocab = ["ville", "projet", "budget", "quartier", "école", "marché", "réforme", "transport", "voisin", "parc"]
    return {
        "theme": f"thème unique {n}",
        "script": " ".join(rng.choice(vocab) + str(rng.randint(0, 99999)) for _ in range((lo + hi) // 2)),
        "question": f"Question numéro {n} sur le document ?",
        "options": [f"Option critique {n} {k}" for k in "wxyz"],
        "correct_answer": target,
        "explanation": "Le locuteur le dit clairement.",
    }


@pytest.fixture()
def fresh_listening(monkeypatch):
    monkeypatch.setattr(ls, "HISTORY", ls._History())
    monkeypatch.setattr(ls, "STEMS", aq.StemHistory(window=30))
    monkeypatch.setattr(ls, "LISTENING_FORMATS", {lvl: [("une chronique", False)] for lvl in ls.LEVELS})


def test_listening_regenerates_when_answer_is_guessable(monkeypatch, fresh_listening):
    calls = Counter()

    def fake(prompt, temperature=0.7):
        if prompt.startswith("Tu passes un QCM"):
            calls["blind"] += 1
            correct = calls["target"]
            # The first two drafts are guessable without listening; the third is fair.
            return {"guess": correct, "confidence": 0.9 if calls["blind"] <= 2 else 0.2}
        target = prompt.split("placée en position ")[1][0]
        calls["gen"] += 1
        calls["target"] = target
        return _listening_payload("C2", target)

    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    q = ls.build_question("C2", with_audio=False)
    assert calls["gen"] == 3 and calls["blind"] == 3
    assert q.correct_answer == calls["target"]


def test_listening_letter_rotation_survives_rejections(monkeypatch, fresh_listening):
    state = {"blind": 0}

    def fake(prompt, temperature=0.7):
        if prompt.startswith("Tu passes un QCM"):
            state["blind"] += 1
            return {"guess": "A", "confidence": 0.9 if state["blind"] % 2 else 0.1}
        target = prompt.split("placée en position ")[1][0]
        state.setdefault("targets", []).append(target)
        return _listening_payload("B2", target)

    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    monkeypatch.setattr(answer_balance, "_bags", {})  # start the rotation fresh, whatever ran before
    letters = [ls.build_question("B2", with_audio=False).correct_answer for _ in range(40)]
    counts = Counter(letters)
    assert all(counts[letter] == 10 for letter in "ABCD"), counts


def test_listening_rejects_repeated_question_openings(monkeypatch, fresh_listening):
    def fake(prompt, temperature=0.7):
        if prompt.startswith("Tu passes un QCM"):
            return {}
        target = prompt.split("placée en position ")[1][0]
        payload = _listening_payload("B1", target)
        payload["question"] = "Que décide la locutrice pour samedi ?"
        return payload

    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    ls.build_question("B1", with_audio=False)
    with pytest.raises(RuntimeError, match="opening used recently"):
        ls.build_question("B1", with_audio=False)


def test_listening_dialogue_uses_rotated_names(monkeypatch, fresh_listening):
    monkeypatch.setattr(ls, "LISTENING_FORMATS", {lvl: [("un dialogue", True)] for lvl in ls.LEVELS})
    used = []

    def fake(prompt, temperature=0.7):
        if prompt.startswith("Tu passes un QCM"):
            return {}
        target = prompt.split("placée en position ")[1][0]
        a, b = (x.strip() for x in prompt.split("deux personnes, ")[1].split(", avec")[0].split(" et "))
        used.extend([a, b])
        payload = _listening_payload("B1", target)
        words = payload["script"].split()
        quarter = len(words) // 4
        payload["script"] = "\n".join(f"{name} : {' '.join(words[i * quarter:(i + 1) * quarter])}"
                                      for i, name in enumerate([a, b, a, b]))
        return payload

    monkeypatch.setattr(tcf_ai_service, "_generate_json", fake)
    for _ in range(10):
        ls.build_question("B1", with_audio=False)
    assert len(used) == len(set(used)) == 20


@pytest.fixture()
def fresh_reading(monkeypatch):
    monkeypatch.setattr(rs, "_registry", rs.UniquenessRegistry())
    monkeypatch.setattr(rs, "STEMS", aq.StemHistory(window=30))


def _reading_payload(target, n):
    rng = random.Random(n)
    return {
        "text": " ".join(f"mot{rng.randint(0, 10 ** 6)}" for _ in range(225)),
        "question": f"Question {n} sur le texte ?",
        "options": [f"Option nuancée {n} {k}" for k in "wxyz"],
        "correct_answer": target,
        "explanation": "Le texte le dit.",
        "topic": f"sujet {n}",
    }


def test_reading_regenerates_when_answer_is_guessable_and_keeps_letter(monkeypatch, fresh_reading):
    calls = Counter()

    def fake(prompt, temperature):
        if prompt.startswith("Tu passes un QCM"):
            calls["blind"] += 1
            return {"guess": calls["target"], "confidence": 0.9 if calls["blind"] == 1 else 0.1}
        target = re.search(r"position ([A-D]) dans la liste", prompt).group(1)
        calls["gen"] += 1
        calls["target"] = target
        return _reading_payload(target, next(_ids))

    monkeypatch.setattr(rs, "_llm_json", fake)
    q = rs.produce_reading_question("C2")
    assert calls["gen"] == 2
    assert q.correct_answer == calls["target"]


def test_reading_quiz_redone_when_too_many_items_are_guessable(monkeypatch, fresh_reading):
    state = {"quizzes": 0}

    def fake(prompt, temperature):
        if prompt.startswith("Tu passes un QCM"):
            letters = re.findall(r"Q(\d+)\.", prompt)
            # First quiz: every item guessable; second quiz: none.
            guess = [{"guess": "A", "confidence": 0.9 if state["quizzes"] == 1 else 0.0} for _ in letters]
            return {"guesses": guess}
        state["quizzes"] += 1
        plan = dict(re.findall(r"Q(\d+)=([A-D])", prompt))
        n = next(_ids)
        return {
            "title": "Titre", "topic": f"sujet {n}",
            "passage": " ".join(f"mot{random.Random(n).randint(0, 10 ** 6)}{i}" for i in range(230)),
            "questions": [{"question": f"Question {i} différente ?", "options": [f"Choix {i}{k}" for k in "wxyz"],
                           "correct_answer": plan[str(i + 1)], "explanation": "Selon le texte."} for i in range(10)],
        }

    monkeypatch.setattr(rs, "_llm_json", fake)
    monkeypatch.setattr(aq, "BLIND_LEVELS", ("B2",))  # B2 is not blind-checked by default (latency)
    # Make every item's answer "A" so the confident blind guesses in quiz 1 hit.
    monkeypatch.setattr(rs, "_quiz_letters", lambda count=10: ["A"] * count)
    quiz = rs.produce_passage_quiz("B2")
    assert state["quizzes"] == 2 and len(quiz.questions) == 10


def test_blind_guess_call_only_runs_where_tone_gives_answers_away():
    calls = []

    def llm(prompt, temperature):
        calls.append(1)
        return {"guess": "A", "confidence": 0.99}

    opts = ["Elle approuve le projet municipal.", "Elle réclame un autre calendrier.",
            "Elle doute du budget annoncé.", "Elle propose un vote public."]
    assert aq.option_problem("B2", "Que pense-t-elle ?", opts, 0, llm) is None and calls == []
    assert aq.option_problem("C2", "Que pense-t-elle ?", opts, 0, llm) and calls == [1]
