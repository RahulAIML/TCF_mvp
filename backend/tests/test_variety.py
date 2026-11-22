"""Voice pairs and formats rotate per learner, and a choice is not repeated three times running."""
import math
from collections import Counter

import variety
from listening_service import assign_voices


def _entropy(labels: list[str]) -> float:
    counts = Counter(labels)
    total = len(labels)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def test_format_choices_rotate_and_cover_the_list():
    options = ["annonce", "dialogue", "message", "interview", "débat", "chronique"]
    learner = "guest:variety-formats"
    picked = [variety.choose("listening_format:B1", options, learner) for _ in range(60)]
    assert all(item in options for item in picked)
    assert len(set(picked)) == len(options)
    assert not any(picked[i] == picked[i + 1] == picked[i + 2] for i in range(len(picked) - 2))
    # Six equally likely formats have entropy log2(6) ≈ 2.58. Skipping the previous one stays well above 2.
    assert _entropy(picked) > 2.0


def test_every_module_has_more_than_one_format():
    catalogs = {
        "writing_task1": variety.WRITING_TASK1_FORMS,
        "writing_task2": variety.WRITING_TASK2_FORMS,
        "vocab": variety.VOCAB_TOPICS,
        "grammar": variety.GRAMMAR_FOCI,
        **{f"speaking:{key}": value for key, value in variety.SPEAKING_SITUATIONS.items()},
    }
    assert len(variety.LISTENING_PAIRS) >= 4
    for name, options in catalogs.items():
        assert len(options) >= 3, name
        learner = f"guest:variety-{name}"
        picked = [variety.choose(name, options, learner) for _ in range(12)]
        assert len(set(picked)) >= 3
        assert not any(picked[i] == picked[i + 1] == picked[i + 2] for i in range(len(picked) - 2))


def test_consecutive_dialogues_do_not_reuse_the_voice_pair():
    learner = "guest:variety-voices"
    pairs = []
    for _ in range(12):
        voices = assign_voices(["Marc", "Sophie"], learner=learner)
        assert voices["Marc"] != voices["Sophie"]
        assert voices["Marc"].split("-")[2] == "male"
        assert voices["Sophie"].split("-")[2] == "female"
        import tts_service
        left = tts_service.get_voice(voices["Marc"])
        right = tts_service.get_voice(voices["Sophie"])
        assert left["pitch_semitones"] == right["pitch_semitones"] == 0
        assert left["gemini_voice_name"] != right["gemini_voice_name"]
        pairs.append(variety.pair_key(voices["Marc"], voices["Sophie"]))
    assert all(pairs[i] != pairs[i + 1] for i in range(len(pairs) - 1))
    assert len(set(pairs)) >= 4
    used = {voice for pair in pairs for voice in pair.split("|")}
    assert len(used) >= 6


def test_same_gender_dialogue_keeps_two_different_voices():
    learner = "guest:variety-same-gender"
    for names in (["François", "Paul"], ["Claire", "Léa"]):
        voices = assign_voices(names, learner=learner)
        assert voices[names[0]] != voices[names[1]]
        assert voices[names[0]].split("-")[2] == voices[names[1]].split("-")[2]


def test_without_a_learner_the_classic_contrast_stays():
    voices = assign_voices(["François", "Paul"])
    import tts_service
    first = tts_service.get_voice(voices["François"])
    second = tts_service.get_voice(voices["Paul"])
    assert {first["gemini_voice_name"], second["gemini_voice_name"]} == {"Charon", "Orus"}
    assert first["pitch_semitones"] == second["pitch_semitones"] == 0
