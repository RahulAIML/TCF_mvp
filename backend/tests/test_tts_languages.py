"""Four languages, their voices, and that every generated file is a real MP3."""
import os

import pytest

import tts_service as tts


def test_four_languages_each_with_four_voices():
  langs = {l["code"]: l for l in tts.list_languages()}
  assert set(langs) == {"fr", "en", "es", "pt"}
  assert [langs[c]["name"] for c in ("fr", "en", "es", "pt")] == ["French", "English", "Spanish", "Portuguese"]
  for code in langs:
    voices = tts.list_active_voices(code)
    assert {v["gender"] for v in voices} == {"male", "female"}
    assert all(v["language"] == code for v in voices)
    assert len(voices) >= 12 if code == "fr" else len(voices) == 4
    assert all(tts.get_voice(v["id"])["pitch_semitones"] == 0 for v in voices)


def test_french_adult_pool_is_balanced_and_unshifted():
  voices = tts.list_active_voices("fr")
  males = [v for v in voices if v["gender"] == "male"]
  females = [v for v in voices if v["gender"] == "female"]
  assert len(voices) >= 12
  assert len(males) >= 6 and len(females) >= 6
  names = [tts.get_voice(v["id"])["gemini_voice_name"] for v in voices]
  assert len(names) == len(set(names))
  assert "Charon" in names and "Kore" in names
  assert "Leda" not in names and "Fenrir" not in names
  assert "Puck" not in names and "Gacrux" not in names
  assert tts.get_voice("fr-FR-male-1")["gemini_voice_name"] == "Charon"
  assert tts.get_voice("fr-FR-male-2")["gemini_voice_name"] == "Orus"
  assert tts.get_voice("fr-FR-male-1")["pitch_semitones"] == 0
  assert "neutral standard French" in tts.get_voice("fr-FR-female-1")["gemini_style"]
  assert "30 and 50" in tts.get_voice("fr-FR-male-1")["gemini_style"]


def test_all_voices_have_unique_ids_and_a_gemini_voice():
  voices = list(tts.VOICE_REGISTRY.values())
  assert len({v["id"] for v in voices}) == len(voices) == 28
  assert all(v["gemini_voice_name"] and v["pitch_semitones"] == 0 for v in voices)


@pytest.mark.parametrize("raw,code", [
  ("fr", "fr"), ("FR", "fr"), ("fr-FR", "fr"), ("French", "fr"), ("français", "fr"),
  ("en", "en"), ("en_US", "en"), ("english", "en"),
  ("es", "es"), ("Spanish", "es"), ("español", "es"),
  ("pt", "pt"), ("pt-BR", "pt"), ("Portuguese", "pt"), ("português", "pt"),
])
def test_normalize_language(raw, code):
  assert tts.normalize_language(raw) == code


@pytest.mark.parametrize("raw", [None, "", "  ", "de", "klingon", "zh-CN"])
def test_normalize_language_rejects_unsupported(raw):
  assert tts.normalize_language(raw) is None


def test_list_voices_for_unknown_language_is_empty():
  assert tts.list_active_voices("de") == []


def test_resolve_voice_by_language_picks_that_languages_first_voice():
  assert tts.resolve_voice(language="es")["id"] == "es-ES-male-1"
  assert tts.resolve_voice(language="pt-BR")["id"] == "pt-BR-male-1"


def test_resolve_voice_defaults_to_french():
  assert tts.resolve_voice()["id"] == "fr-FR-male-1"


def test_resolve_voice_gender():
  assert tts.resolve_voice(language="en", gender="female")["id"] == "en-US-female-1"
  with pytest.raises(ValueError, match="male"):
    tts.resolve_voice(language="en", gender="robot")


def test_resolve_voice_by_id_alone_uses_its_own_language():
  assert tts.resolve_voice(voice_id="pt-BR-female-2")["language"] == "pt"


def test_resolve_voice_rejects_a_voice_from_another_language_and_says_what_exists():
  with pytest.raises(ValueError) as e:
    tts.resolve_voice(language="es", voice_id="fr-FR-male-1")
  assert "es-ES-female-1" in str(e.value)


def test_resolve_voice_errors_list_the_options():
  with pytest.raises(ValueError) as e:
    tts.resolve_voice(voice_id="nope")
  assert "Unknown voice" in str(e.value)
  with pytest.raises(ValueError) as e:
    tts.resolve_voice(language="de")
  assert "fr (French)" in str(e.value) and "pt (Portuguese)" in str(e.value)


def test_pcm_is_encoded_as_a_real_mp3():
  pcm = b"\x00\x00" * tts.GEMINI_SAMPLE_RATE  # one second of silence
  mp3 = tts._pcm_to_mp3(pcm)
  assert mp3 is not None and len(mp3) > 100
  assert mp3[:3] == b"ID3" or mp3[0] == 0xFF and (mp3[1] & 0xE0) == 0xE0  # ID3 tag or an MPEG frame sync


def test_gemini_output_is_saved_as_mp3(monkeypatch):
  calls = []

  class _Audio:
    data = b"\x00\x00" * 4800

  class _Interaction:
    output_audio = _Audio()

  class _Interactions:
    def create(self, **kw):
      calls.append(kw)
      return _Interaction()

  class _Client:
    def __init__(self, **kw):
      self.interactions = _Interactions()
      self.models = None

  import sys, types
  fake_genai = types.ModuleType("google.genai")
  fake_genai.Client = _Client
  fake_types = types.ModuleType("google.genai.types")
  fake_types.HttpOptions = lambda **kw: kw
  fake_genai.types = fake_types
  monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
  monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
  import google
  monkeypatch.setattr(google, "genai", fake_genai, raising=False)
  monkeypatch.setattr(tts, "_GEMINI_API_KEY", "x")
  monkeypatch.setattr(tts, "_gemini_tts_client", None)

  result = tts.synthesize("Hola", "es-ES-female-1")
  assert result["extension"] == "mp3" and result["mime_type"] == "audio/mpeg" and result["provider"] == "gemini"
  assert result["provider_voice"] == "Kore"
  assert calls[0]["generation_config"]["speech_config"] == [{"voice": "Kore"}]
  assert calls[0]["response_format"] == {"type": "audio"}


def test_save_audio_long_names_are_unguessable_and_short_ones_keep_the_old_shape():
  res = {"data": b"abc", "extension": "mp3", "mime_type": "audio/mpeg", "provider": "x"}
  name, url = tts.save_audio(res, "es-ES-male-1", long_name=True)
  assert url == f"/audio/{name}" and name.startswith("tts_es-ES-male-1_") and name.endswith(".mp3")
  assert len(name.split("_")[-1].split(".")[0]) == 32
  short, _ = tts.save_audio(res, "es-ES-male-1")
  assert len(short.split("_")[-1].split(".")[0]) == 8
  assert os.path.exists(os.path.join(tts.AUDIO_STORAGE_PATH, name))


def test_both_providers_failing_gives_one_clear_error():
  with pytest.raises(RuntimeError, match="Audio generation failed"):
    tts.synthesize("hello", "en-US-male-1")  # no API keys in the test environment


def test_empty_and_too_long_text_are_refused():
  with pytest.raises(ValueError):
    tts.synthesize("   ", "fr-FR-male-1")
  with pytest.raises(ValueError, match="maximum"):
    tts.synthesize("x" * (tts.MAX_TEXT_LENGTH + 1), "fr-FR-male-1")


def test_voices_stay_at_natural_pitch():
  deep = tts.get_voice("fr-FR-male-1")
  bright = tts.get_voice("fr-FR-male-2")
  assert deep["pitch_semitones"] == bright["pitch_semitones"] == 0
  assert deep["gemini_voice_name"] != bright["gemini_voice_name"]
  women = (tts.get_voice("fr-FR-female-1"), tts.get_voice("fr-FR-female-2"))
  assert women[0]["pitch_semitones"] == women[1]["pitch_semitones"] == 0
  assert women[0]["gemini_voice_name"] != women[1]["gemini_voice_name"]


def test_pitch_shift_is_not_applied():
  import math
  import struct
  rate = 8000
  pcm = b"".join(
    struct.pack("<h", int(6000 * math.sin(2 * math.pi * 200.0 * i / rate)))
    for i in range(rate)
  )
  assert tts.shift_pitch_pcm(pcm, 12, sample_rate=rate) == pcm
