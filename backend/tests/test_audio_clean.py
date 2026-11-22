"""Clean the loud burst at the end (and the click at the start) of generated speech, and nothing else."""
import sys
import time
import types

import numpy as np
import pytest

import audio_clean as ac
import tts_service as tts

RATE = 24000
rng = np.random.default_rng(7)


# ------------------------------- synthetic speech -------------------------------

def _scale(x, rms):
  return x * (rms / max(1e-9, float(np.sqrt(np.mean(x ** 2)))))


def vowel(ms, f0=140, rms=3000):
  """A voiced sound: harmonics of f0 with a formant-like tilt, 10 ms attack and release."""
  t = np.arange(int(RATE * ms / 1000)) / RATE
  x = sum(np.sin(2 * np.pi * k * f0 * t + k) / k for k in range(1, 22))
  env = np.minimum(1, np.minimum(np.arange(len(t)) / (RATE * 0.01), (len(t) - np.arange(len(t))) / (RATE * 0.01)))
  return _scale(x * env, rms)


def fricative(ms, rms=700):
  """An 's' or 'ch': quiet broadband noise (well under the level of vowels)."""
  n = rng.standard_normal(int(RATE * ms / 1000))
  return _scale(np.diff(n, prepend=0), rms)


def noise_burst(ms, rms=3500):
  return _scale(rng.standard_normal(int(RATE * ms / 1000)), rms)


def gap(ms):
  return rng.standard_normal(int(RATE * ms / 1000)) * 2


def sentence(words=6, end_with=None):
  parts = [gap(250)]
  for i in range(words):
    parts += [vowel(180 + 30 * (i % 3), f0=120 + 12 * i), vowel(120, f0=150 + 5 * i), gap(35)]
    if i % 2 == 1:
      parts.append(gap(120))
  if end_with is not None:
    parts.append(end_with)
  return np.concatenate(parts)


def pcm(x):
  return np.clip(np.round(x), -32768, 32767).astype("<i2").tobytes()


def samples(b):
  return np.frombuffer(b, dtype="<i2").astype(float)


def rms(x):
  return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def tail_rms(x, ms):
  return rms(x[-int(RATE * ms / 1000):])


def edge_noise_ms(y, where, window_ms=300):
  """How many ms of the first/last `window_ms` are LOUD, flat and unvoiced, i.e. noise rather than speech."""
  frame = RATE // 100
  body = ac._speech_level(ac._frame_rms(y, frame))
  seg = y[-int(RATE * window_ms / 1000):] if where == "tail" else y[: int(RATE * window_ms / 1000)]
  r = ac._frame_rms(seg, frame)
  bad = 0
  for i in range(len(r)):
    if r[i] < 0.5 * body:
      continue
    win = ac._window(seg, i * frame + frame // 2, int(RATE * 0.04))
    if ac._voicing(win, RATE) < ac.VOICED_MAX and ac._flatness(win, RATE) > ac.FLATNESS_MIN:
      bad += 10
  return bad


# ------------------------------- the cases -------------------------------

def test_a_loud_burst_after_the_last_word_is_removed():
  speech = sentence()
  noisy = np.concatenate([speech, noise_burst(200)])
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  y = samples(out)
  assert report.changed and 150 <= report.burst_tail_ms <= 260
  assert len(y) < len(noisy) - RATE * 0.18                       # the 200 ms burst is gone
  assert edge_noise_ms(noisy, "tail") >= 150                     # the input really does have a noisy ending
  assert edge_noise_ms(y, "tail") == 0                           # the output does not
  assert rms(y[-int(RATE * 0.015):]) < 0.1 * rms(speech)         # and fades to silence


def test_a_burst_straight_after_a_short_gap_is_removed_too():
  noisy = np.concatenate([sentence(), gap(40), noise_burst(220)])
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  assert report.burst_tail_ms >= 150
  assert edge_noise_ms(samples(out), "tail") == 0


def test_noise_followed_by_trailing_silence_is_removed():
  noisy = np.concatenate([sentence(), noise_burst(200), gap(300)])
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  assert report.burst_tail_ms >= 150
  assert len(samples(out)) < len(noisy) - RATE * 0.4


def test_a_click_and_noise_at_the_very_start_are_removed():
  speech = sentence()
  noisy = np.concatenate([noise_burst(90), gap(20), speech])
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  y = samples(out)
  assert report.burst_head_ms >= 60
  assert edge_noise_ms(noisy, "head") >= 60 and edge_noise_ms(y, "head") == 0   # noisy in, clean out


def test_both_ends_at_once():
  noisy = np.concatenate([noise_burst(100), gap(30), sentence(), noise_burst(200)])
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  assert report.burst_head_ms > 0 and report.burst_tail_ms > 0
  y = samples(out)
  assert edge_noise_ms(y, "tail") == 0 and edge_noise_ms(y, "head") == 0


def test_clean_speech_is_kept_apart_from_edge_silence_and_the_fades():
  speech = sentence()
  out, report = ac.clean_pcm(pcm(speech), RATE)
  y = samples(out)
  assert report.burst_tail_ms == 0 and report.burst_head_ms == 0
  # the body is untouched: the middle two seconds match the input sample for sample (up to rounding and DC)
  a = int(RATE * 0.4)
  offset = int(round(report.trimmed_head_ms * RATE / 1000))
  src = speech[offset + a: offset + a + RATE * 2]
  dst = y[a: a + RATE * 2]
  assert np.corrcoef(src, dst)[0, 1] > 0.9999
  assert len(y) > len(speech) - RATE * 0.5


def test_a_word_that_ends_in_a_quiet_fricative_is_not_cut():
  with_s = np.concatenate([sentence(end_with=np.concatenate([vowel(140), fricative(180)]))])
  without = np.concatenate([sentence(end_with=vowel(140))])
  out, report = ac.clean_pcm(pcm(with_s), RATE)
  assert report.burst_tail_ms == 0
  # the 's' (about 180 ms) is still there
  assert len(samples(out)) > len(samples(ac.clean_pcm(pcm(without), RATE)[0])) + RATE * 0.12


def test_a_loud_but_voiced_ending_is_not_cut():
  x = np.concatenate([sentence(), vowel(250, f0=200, rms=5000)])   # a loud, held vowel
  out, report = ac.clean_pcm(pcm(x), RATE)
  assert report.burst_tail_ms == 0
  assert len(samples(out)) > len(x) - RATE * 0.3


def test_silence_too_short_and_unclear_audio_are_returned_unchanged():
  for data in (pcm(np.zeros(RATE * 2)), pcm(sentence())[: RATE // 10], b"", b"\x01", pcm(rng.standard_normal(RATE) * 5)):
    out, report = ac.clean_pcm(data, RATE)
    assert out == data and report.changed is False


def test_odd_length_input_does_not_crash():
  data = pcm(np.concatenate([sentence(), noise_burst(200)])) + b"\x00"
  out, report = ac.clean_pcm(data, RATE)
  assert report.changed and len(out) % 2 == 0


def test_the_output_never_clips_or_wraps():
  x = np.concatenate([sentence() * 8, noise_burst(200, rms=12000)])
  out, _ = ac.clean_pcm(pcm(x), RATE)
  y = samples(out)
  assert np.abs(y).max() <= 32767


def test_five_minutes_of_audio_is_cleaned_quickly():
  long = np.concatenate([sentence(8) for _ in range(75)] + [noise_burst(200)])
  assert len(long) > RATE * 240
  t0 = time.time()
  out, report = ac.clean_pcm(pcm(long), RATE)
  assert time.time() - t0 < 4
  assert report.burst_tail_ms >= 150


def test_the_switch_turns_it_off(monkeypatch):
  monkeypatch.setenv("TTS_CLEAN_AUDIO", "0")
  assert ac.enabled() is False
  monkeypatch.setenv("TTS_CLEAN_AUDIO", "1")
  assert ac.enabled() is True
  monkeypatch.delenv("TTS_CLEAN_AUDIO")
  assert ac.enabled() is True


# ------------------------------- through the real pipeline -------------------------------

def _fake_gemini(monkeypatch, pcm_bytes):
  class _Inline:
    data = pcm_bytes

  class _Part:
    inline_data = _Inline()

  class _Resp:
    candidates = [type("C", (), {"content": type("K", (), {"parts": [_Part()]})()})()]

  class _Models:
    def generate_content(self, **kw):
      return _Resp()

  class _Client:
    def __init__(self, **kw):
      self.models = _Models()

  fake_genai = types.ModuleType("google.genai")
  fake_genai.Client = _Client
  fake_types = types.ModuleType("google.genai.types")
  for n in ("GenerateContentConfig", "SpeechConfig", "VoiceConfig", "PrebuiltVoiceConfig"):
    setattr(fake_types, n, lambda **kw: kw)
  fake_genai.types = fake_types
  monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
  monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
  import google
  monkeypatch.setattr(google, "genai", fake_genai, raising=False)
  monkeypatch.setattr(tts, "_GEMINI_API_KEY", "x")


def _decode(mp3):
  miniaudio = pytest.importorskip("miniaudio")
  d = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=RATE)
  return np.frombuffer(d.samples, dtype="<i2").astype(float)


def test_the_mp3_from_gemini_has_no_noise_at_either_end(monkeypatch):
  speech = sentence()
  dirty = pcm(np.concatenate([noise_burst(90), gap(20), speech, noise_burst(200)]))
  _fake_gemini(monkeypatch, dirty)

  result = tts.synthesize("Bonjour", "fr-FR-male-1")
  assert result["extension"] == "mp3"
  y = _decode(result["data"])
  assert edge_noise_ms(y, "tail") == 0
  assert edge_noise_ms(y, "head") == 0


def test_the_same_audio_without_cleaning_does_have_the_noise(monkeypatch):
  """Guards the test above: with cleaning off the burst IS in the MP3, so the check above proves something."""
  dirty = pcm(np.concatenate([noise_burst(90), gap(20), sentence(), noise_burst(200)]))
  _fake_gemini(monkeypatch, dirty)
  monkeypatch.setenv("TTS_CLEAN_AUDIO", "0")
  y = _decode(tts.synthesize("Bonjour", "fr-FR-male-1")["data"])
  assert edge_noise_ms(y, "tail") >= 100 and edge_noise_ms(y, "head") >= 50


def test_a_cleaning_failure_never_breaks_generation(monkeypatch):
  _fake_gemini(monkeypatch, pcm(sentence()))
  monkeypatch.setattr(ac, "clean_pcm", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
  result = tts.synthesize("Bonjour", "fr-FR-male-1")
  assert result["extension"] == "mp3" and len(result["data"]) > 1000


def test_a_burst_with_codec_ramps_at_the_edges_is_still_found():
  """The same audio after an MP3 round trip (what a listener's file looks like): the burst has soft edges."""
  miniaudio = pytest.importorskip("miniaudio")
  dirty = pcm(np.concatenate([noise_burst(90), gap(20), sentence(), noise_burst(200)]))
  mp3 = tts._pcm_to_mp3(dirty)
  d = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=RATE)
  out, report = ac.clean_pcm(bytes(d.samples), RATE)
  y = samples(out)
  assert report.burst_head_ms >= 60 and report.burst_tail_ms >= 150
  assert edge_noise_ms(y, "head") == 0 and edge_noise_ms(y, "tail") == 0


def test_a_full_scale_tail_burst_is_gone_from_the_mp3():
  """The burst seen in production is ~0.06-0.18 s at the rails, after the last word."""
  speech = sentence()
  burst = np.clip(rng.standard_normal(int(RATE * 0.12)) * 22000, -32767, 32767)
  dirty = pcm(np.concatenate([speech, burst]))
  cleaned, report = ac.clean_pcm(dirty, RATE)
  assert report.burst_tail_ms >= 60
  assert edge_noise_ms(samples(cleaned), "tail") == 0
  mp3 = tts.polish_mp3(tts._pcm_to_mp3(dirty))
  assert edge_noise_ms(_decode(mp3), "tail") == 0


def test_the_padding_around_the_speech_is_true_silence_never_leftover_noise():
  """A burst glued to the last word must not leak back in through the padding."""
  noisy = np.concatenate([noise_burst(90), sentence()[RATE // 4:], noise_burst(200)])   # no gap on either side
  out, report = ac.clean_pcm(pcm(noisy), RATE)
  y = samples(out)
  assert report.burst_head_ms > 0 and report.burst_tail_ms > 0
  assert np.abs(y[: int(RATE * 0.05)]).max() == 0
  assert np.abs(y[-int(RATE * 0.05):]).max() == 0
