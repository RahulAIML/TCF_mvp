"""
Look at the first and last half second of an MP3 and, optionally, write a cleaned copy.

  cd backend
  pip install -r requirements-dev.txt
  python scripts/check_audio_ends.py path/to/file.mp3                 # report only
  python scripts/check_audio_ends.py path/to/file.mp3 cleaned.mp3     # also write the cleaned MP3

The report lists every 10 ms frame of the first and last 400 ms: its level, whether it has a pitch ("voiced") and
how noise-like it is ("flat"), and marks the frames the server's cleaner (audio_clean.py) treats as a noise burst.
The cleaned copy goes through the exact same code the server runs on Gemini audio, so listening to it tells you
what the server will now produce. (The file is decoded and re-encoded, so it is a check, not a master copy.)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audio_clean as ac  # noqa: E402

RATE = 24000
FRAME = RATE // 100


def load(path: str) -> np.ndarray:
  import miniaudio
  d = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=RATE)
  return np.frombuffer(d.samples, dtype="<i2").astype(float)


def describe(y: np.ndarray, label: str, tail: bool) -> int:
  rms = ac._frame_rms(y - np.mean(y), FRAME)
  ref = ac._speech_level(rms)
  seg = y[-RATE * 4 // 10:] if tail else y[: RATE * 4 // 10]
  r = ac._frame_rms(seg - np.mean(y), FRAME)
  print(f"\n{label} (speech level {ref:.0f}; frames are 10 ms)")
  print("   ms    level  %speech  voiced  flat   verdict")
  bad = 0
  for i in range(len(r)):
    win = ac._window(seg - np.mean(y), i * FRAME + FRAME // 2, int(RATE * 0.04))
    v, f = ac._voicing(win, RATE), ac._flatness(win, RATE)
    burst = r[i] >= ac.TAIL_LOUD_FRACTION * ref and v < ac.VOICED_MAX and f > ac.FLATNESS_MIN
    bad += burst
    ms = (i * 10) if not tail else (-(len(r) - i) * 10)
    if i % 2 == 0 or burst:
      print(f"{ms:6d} {r[i]:8.0f} {100 * r[i] / max(ref, 1):7.0f}% {v:7.2f} {f:5.2f}   {'NOISE BURST' if burst else ''}")
  print(f"-> {bad * 10} ms of loud, flat, unvoiced frames in the {'last' if tail else 'first'} 400 ms")
  return bad * 10


def main() -> int:
  if len(sys.argv) < 2:
    print(__doc__)
    return 2
  y = load(sys.argv[1])
  print(f"{sys.argv[1]}: {len(y) / RATE:.2f} s")
  head = describe(y, "START", tail=False)
  tail = describe(y, "END", tail=True)
  cleaned, report = ac.clean_pcm(np.clip(y, -32768, 32767).astype("<i2").tobytes(), RATE)
  print(f"\nCleaner: head -{report.trimmed_head_ms:.0f} ms (burst {report.burst_head_ms:.0f} ms), "
        f"tail -{report.trimmed_tail_ms:.0f} ms (burst {report.burst_tail_ms:.0f} ms), changed={report.changed}")
  if len(sys.argv) > 2:
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    with open(sys.argv[2], "wb") as f:
      f.write(bytes(enc.encode(cleaned)) + bytes(enc.flush()))
    print(f"Wrote {sys.argv[2]}")
  if head == 0 and tail == 0:
    print("\nNo loud noise-like frames at either end: this file's edges look clean to the detector.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
