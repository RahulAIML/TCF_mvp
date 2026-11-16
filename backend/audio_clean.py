"""
audio_clean.py — clean the edges of generated speech before it is encoded as MP3.

Why: the encoder is not the cause (a clean tone encodes with no burst at either end). The voice provider's raw
audio can carry a short loud burst of noise right after the last word, and a click/pop at the very start. That
ends up in every MP3 made from it. This module removes it from the raw 16-bit mono PCM, then fades the start
and end so nothing is cut abruptly.

What it does (all on the raw PCM, only the first and last ~half second are analysed):
  1. Removes DC offset.
  2. Finds how loud the speech normally is (90th percentile of the 10 ms frame levels).
  3. At the END, and at the START, drops a short run (up to 400 ms) of frames that are all of:
       - loud (well above a typical fricative: at least TAIL_LOUD_FRACTION of the speech level),
       - noise-like (flat spectrum), and
       - not voiced (no pitch: no periodicity in the 60-400 Hz range).
     Speech is voiced or, for fricatives such as "s" and "ch", quieter than vowels, so real words are kept; a burst of
     broadband noise is loud, flat and has no pitch.
  4. Replaces the silence at both ends with a short pad of true silence, and applies a 12 ms fade-in and a 60 ms
     fade-out to the speech itself.

It never raises into the caller's path: clean_pcm() returns the input unchanged when the audio has no clear
speech, is too short, or anything goes wrong. Turn it off with TTS_CLEAN_AUDIO=0.
"""

import logging
import os
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("audio_clean")

FRAME_MS = 10
MAX_EDGE_MS = 400            # the longest burst that is treated as an artifact
MIN_BURST_MS = 30            # shorter than this is a click: handled by the fades
TAIL_LOUD_FRACTION = 0.5     # a burst frame must be at least this fraction of the speech level
FLATNESS_MIN = 0.30          # spectral flatness (0 = a pure tone, 1 = white noise)
VOICED_MAX = 0.45            # normalised autocorrelation peak; above this the frame has a pitch
SILENCE_FRACTION = 0.03      # below this fraction of the speech level a frame counts as silence
KEEP_PAD_MS = 60             # silence kept before the first and after the last sound
FADE_IN_MS = 12
FADE_OUT_MS = 60
MIN_SPEECH_MS = 150
TRANSITION_FRAMES = 3        # quiet-but-not-silent frames tolerated between the silence and a burst (codec ramps)


@dataclass
class CleanReport:
  trimmed_head_ms: float = 0.0
  trimmed_tail_ms: float = 0.0
  burst_head_ms: float = 0.0
  burst_tail_ms: float = 0.0
  changed: bool = False


def enabled() -> bool:
  return os.getenv("TTS_CLEAN_AUDIO", "1").strip().lower() not in ("0", "false", "no", "off")


def _frame_rms(x: np.ndarray, frame: int) -> np.ndarray:
  n = len(x) // frame
  if n == 0:
    return np.zeros(0)
  blocks = x[: n * frame].reshape(n, frame)
  return np.sqrt(np.mean(blocks ** 2, axis=1))


def _window(x: np.ndarray, centre: int, length: int) -> np.ndarray:
  lo = max(0, centre - length // 2)
  hi = min(len(x), lo + length)
  lo = max(0, hi - length)
  return x[lo:hi]


def _flatness(win: np.ndarray, rate: int) -> float:
  """Spectral flatness in the speech band (200 Hz - 8 kHz): geometric / arithmetic mean of the power spectrum."""
  if len(win) < 64:
    return 0.0
  spec = np.abs(np.fft.rfft(win * np.hanning(len(win)))) ** 2
  freqs = np.fft.rfftfreq(len(win), 1.0 / rate)
  band = spec[(freqs >= 200) & (freqs <= min(8000, rate / 2 - 1))]
  band = band[band > 0]
  if len(band) < 4:
    return 0.0
  return float(np.exp(np.mean(np.log(band))) / np.mean(band))


def _voicing(win: np.ndarray, rate: int) -> float:
  """Normalised autocorrelation peak for pitch lags 60-400 Hz: high for voiced speech, low for noise."""
  if len(win) < int(rate / 60) * 2:
    return 0.0
  w = win - np.mean(win)
  energy = float(np.dot(w, w))
  if energy <= 0:
    return 0.0
  n = 1 << (2 * len(w) - 1).bit_length()
  f = np.fft.rfft(w, n)
  ac = np.fft.irfft(f * np.conj(f), n)[: len(w)]
  lo, hi = int(rate / 400), int(rate / 60)
  return float(np.max(ac[lo:hi]) / ac[0])


def _is_burst_frame(x: np.ndarray, i: int, frame: int, rms: np.ndarray, ref: float, rate: int) -> bool:
  if rms[i] < TAIL_LOUD_FRACTION * ref:
    return False
  win = _window(x, i * frame + frame // 2, int(rate * 0.040))
  return _voicing(win, rate) < VOICED_MAX and _flatness(win, rate) > FLATNESS_MIN


def _speech_level(rms: np.ndarray) -> float:
  if len(rms) == 0:
    return 0.0
  loud = rms[rms > 0.02 * rms.max()]
  return float(np.percentile(loud, 90)) if len(loud) else 0.0


def clean_pcm(pcm: bytes, rate: int = 24000) -> tuple[bytes, CleanReport]:
  """Clean raw 16-bit little-endian mono PCM. Returns (pcm, report); the input itself if nothing needed doing."""
  report = CleanReport()
  try:
    if len(pcm) < 2 * rate * MIN_SPEECH_MS // 1000:
      return pcm, report
    raw = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
    x = raw.astype(np.float64)
    x = x - np.mean(x)
    frame = rate * FRAME_MS // 1000
    rms = _frame_rms(x, frame)
    ref = _speech_level(rms)
    if len(rms) < MIN_SPEECH_MS // FRAME_MS or ref < 50:  # no clear speech (silence, or too quiet to judge)
      return pcm, report

    silence = SILENCE_FRACTION * ref
    start, end = 0, len(rms)                       # in frames: [start, end)

    # ---- END: skip trailing silence, then drop a trailing run of loud, flat, unvoiced frames
    while end > start and rms[end - 1] < silence:
      end -= 1
    run = 0
    j = end - 1
    max_frames = MAX_EDGE_MS // FRAME_MS
    skipped = 0
    while j >= start and skipped < TRANSITION_FRAMES and rms[j] < TAIL_LOUD_FRACTION * ref:   # a decay ramp
      j -= 1
      skipped += 1
    while j >= start and run < max_frames and _is_burst_frame(x, j, frame, rms, ref, rate):
      run += 1
      j -= 1
    if run * FRAME_MS >= MIN_BURST_MS and j >= start:
      end = j + 1
      report.burst_tail_ms = run * FRAME_MS
      while end > start and rms[end - 1] < silence:   # silence the burst was sitting after
        end -= 1

    # ---- START: skip leading silence, then drop a leading run of loud, flat, unvoiced frames
    while start < end and rms[start] < silence:
      start += 1
    run = 0
    j = start
    skipped = 0
    while j < end and skipped < TRANSITION_FRAMES and rms[j] < TAIL_LOUD_FRACTION * ref:   # an onset ramp
      j += 1
      skipped += 1
    while j < end and run < max_frames and _is_burst_frame(x, j, frame, rms, ref, rate):
      run += 1
      j += 1
    if run * FRAME_MS >= MIN_BURST_MS and j < end:
      start = j
      report.burst_head_ms = run * FRAME_MS
      while start < end and rms[start] < silence:
        start += 1

    if end - start < MIN_SPEECH_MS // FRAME_MS:   # nothing sensible left: do not touch the audio
      return pcm, CleanReport()

    # The speech itself, faded at both ends, with a short pad of TRUE silence (zeros) around it. The pad is never
    # copied from the original: right after a removed burst the original is noise, not silence.
    seg = x[start * frame: end * frame].copy()
    fi = min(len(seg) // 4, rate * FADE_IN_MS // 1000)
    fo = min(len(seg) // 4, rate * FADE_OUT_MS // 1000)
    if fi > 0:
      seg[:fi] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi))
    if fo > 0:
      seg[-fo:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))
    pad = np.zeros(rate * KEEP_PAD_MS // 1000)
    out = np.concatenate([pad, seg, pad])

    # Net change at each end, in ms (the pad is silence we add, so this can be negative if the start was tight).
    report.trimmed_head_ms = (start * frame - len(pad)) * 1000.0 / rate
    report.trimmed_tail_ms = (len(x) - end * frame - len(pad)) * 1000.0 / rate
    report.changed = True
    return np.clip(np.round(out), -32768, 32767).astype("<i2").tobytes(), report
  except Exception as exc:  # never let cleaning break generation
    logger.warning("audio clean skipped: %s", exc)
    return pcm, CleanReport()
