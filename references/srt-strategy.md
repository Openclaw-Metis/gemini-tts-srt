# SRT timing strategy

## The problem

The Gemini TTS API returns **only audio** (24kHz/16-bit/mono PCM) and **no timestamps**
— unlike Edge TTS, which emits WordBoundary events. So subtitle timing must be derived.

## Three approaches this skill supports

### 1. segmented (default, recommended)
Synthesize each subtitle line as its **own** TTS call, then measure that line's exact
duration directly from the PCM byte count:

```
duration_seconds = len(pcm_bytes) / (sample_rate * 2 * 1)   # 16-bit mono
```

Concatenate the per-line audio (with a small `--gap-ms` silence between lines); the SRT
timeline is the running sum of measured durations.

- Pros: exact timing, subtitle text is the original script (zero ASR error), no ffprobe,
  no model download.
- Cons: one API call per line (more quota); prosody resets at each line boundary.

### 2. single
One TTS call for the whole script (smoother prosody). Per-line timing is then either:
- **proportional** (default): split the measured total duration across lines by each
  line's unit length (chars for CJK, words otherwise); or
- **whisper** (`--align whisper`): run faster-whisper for word-level timestamps and
  re-chunk them against the script lines (greedy accumulation per line's char budget).
  Requires `pip install faster-whisper`; falls back to proportional if unavailable.

- Pros: most natural prosody.
- Cons: timing is approximate (proportional) or needs an extra dependency + model
  download (whisper).

### 3. estimate / dry-run (`--estimate`, `--dry-run-cost`, no synthesis)
Predict per-line durations from the speech-rate table and emit only the SRT + a JSON
report. No API call, no audio. Use it to preview segmentation/timing and to estimate
cost/length before paying for synthesis. `--dry-run-cost` uses the same no-API path and
emphasizes `estimated_api_calls` / `estimated_chunks` for quota planning. Also the
offline self-test path.

## Why text comes from the script, not ASR
Because we already know the exact words, the SRT text is taken verbatim from the script.
Only the **timing** is derived. This avoids the homophone/recognition errors a pure-ASR
subtitle pipeline (Whisper transcription) would introduce — the same reason MoneyPrinter-
Turbo's `edge` subtitle mode is preferred over its `whisper` mode when boundaries exist.

## Line segmentation
`split_into_lines()` is punctuation-first: it segments at sentence-ending marks, then
breaks over-long sentences at soft punctuation (comma/、/；/space) and merges clauses up
to `--max-line-chars`. It only char-wraps a clause that has no inner punctuation and
exceeds the cap, and merges tiny (<4 char) tail fragments back so multi-character names
(e.g. 蚩尤) are less likely to be orphaned across two cards. For CJK set
`--max-line-chars` to ~16–20.

For terms that must remain intact, use `--protect-terms "蚩尤,OpenAI,Gemini 3.1"` or
`--protect-file terms.txt`. Protected terms are temporarily replaced with placeholders
during splitting and restored before SRT output, which gives the line splitter a hard
constraint instead of relying only on punctuation heuristics.

## Release-hardening gates

- Unknown voices fail fast before any API call; run `--list-voices` to inspect the 30
  prebuilt voices.
- Output paths are resolved to absolute paths. `--basename` is sanitized to
  `[A-Za-z0-9._-]` and all artifacts must remain under `--out-dir`.
- Real synthesis writes `<basename>.report.json` as well as printing the same JSON to
  stdout.
- Artifact validation checks cue count, monotonic non-overlapping timestamps, unchanged
  subtitle text, positive PCM duration, and parseable audio output.
- Segmented synthesis is blocked when line count exceeds `--max-api-calls` unless
  `--force` is supplied.
- `--format mp3` falls back to WAV by default if ffmpeg fails; `--strict-format` turns
  that into a non-zero exit for automated pipelines.
