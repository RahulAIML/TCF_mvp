"""C1/C2 items are rejected when the key is guessable from tone or length."""
import listening_service as ls
import quality_guard as q


def test_only_the_correct_option_being_critical_is_rejected():
    options = [
        "le narrateur se réjouit de la réforme",
        "le narrateur décrit la réforme sans juger",
        "le narrateur fustige la réforme",
        "le narrateur explique le calendrier",
    ]
    assert q.choice_problems("C2", options, "C") == ["only the correct option carries a critical stance"]
    # The same shape is acceptable below C1: the rule targets the levels where it dominated.
    assert q.choice_problems("B1", options, "C") == []


def test_equally_critical_distractors_are_accepted():
    options = [
        "il raille le projet",
        "il fustige le projet",
        "il dénonce le projet",
        "il déplore le projet",
    ]
    assert q.choice_problems("C1", options, "B") == []


def test_markedly_longer_correct_option_is_rejected():
    options = [
        "court",
        "bref",
        "une longue reformulation qui développe trois idées distinctes et ajoute un exemple",
        "mince",
    ]
    assert any("longer" in problem for problem in q.choice_problems("C2", options, "C"))


def test_francs_in_a_canadian_scene_are_rejected():
    assert q.anachronism_problems("Le billet coûte 20 francs à Montréal.")
    assert q.anachronism_problems("Le billet coûte 20 dollars à Montréal.") == []
    assert q.anachronism_problems("Un roman du XIXe siècle parle de dix francs.") == []


def test_letter_citations_are_scrubbed():
    cleaned = q.scrub_letter_citations("La réponse B est correcte car le texte le dit.")
    assert "réponse B" not in cleaned
    assert "bonne réponse" in cleaned
    assert q.explanation_problems(cleaned) == []


def test_explanation_must_not_cite_a_letter():
    assert q.explanation_problems("L'option B est exacte.") == ["explanation cites an option letter"]
    assert q.explanation_problems("Le texte dit que le magasin ferme à six heures.") == []


def test_listening_form_passes_then_the_stance_guard_rejects_it():
    payload = {
        "theme": "réforme municipale",
        "script": " ".join(["phrase"] * 140),
        "question": "Quel est le ton?",
        "options": [
            "il décrit les faits",
            "il fustige la décision",
            "il donne la date",
            "il cite un chiffre",
        ],
        "correct_answer": "B",
        "explanation": "Le locuteur rejette la décision.",
    }
    item = ls._validate(payload, "C2", False, ("Marc", "Sophie"), "B")
    problems = q.item_problems("C2", item["options"], item["correct_answer"], item["explanation"], item["script"])
    assert any("critical" in problem for problem in problems)
