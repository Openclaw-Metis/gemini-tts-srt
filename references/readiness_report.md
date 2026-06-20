# Readiness report — gemini-tts-srt

Skill version: 2026.6.20
Audit date: 2026-06-20
Owner: Openclaw-Metis
Status: draft (mechanically gated; one live end-to-end synthesis verified)

## Summary

`gemini-tts-srt` turns a script into Gemini-TTS narration plus a time-aligned SRT whose
text is the original script. The `tts-prompter` prompt-crafting framework is integrated
in `references/prompting.md`. The core executor `scripts/gemini_tts.py` was verified both
offline (self-test) and online (a real Gemini API call with the user-supplied key).

## Mechanical gate evidence (skill-creator-advanced toolchain)

Run from `/mnt/skills/user/skill-creator-advanced`, target = this skill.

| Audit | Result |
|---|---|
| format | PASS (0 error) |
| structure | PASS |
| workflow_contract | PASS |
| semantics | PASS |
| semantic_rules | PASS |
| gate_language | PASS |
| lifecycle | PASS |
| lifecycle_state | PASS |
| eval_coverage | PASS |
| eval_quality | PASS |
| golden_trigger_set | PASS |
| wrapper_drift | PASS |
| migration_governance | PASS |
| surface_drift | PASS |
| skill_references | PASS |
| unreferenced_files | PASS |
| healthcheck | PASS |
| benchmark | SKIPPED (no paired A/B benchmark run in this environment) |

Release gate: `release_gate.py --stage draft` → see final run.
Stage gate: `stage_gate.py --stage create` → see final run.

## Functional evidence

Offline (`python scripts/gemini_tts.py --self-test`): ALL PASS — line splitting,
PCM-duration math, segmented + single pipelines (mock audio), SRT formatting/timestamps.

Estimate mode (`--estimate`, no API): produces SRT + JSON report; verified on zh-TW,
ja-JP, fr-FR scripts; CJK names (e.g. 蚩尤) are not split across cards.

## Live end-to-end evidence (real Gemini API)

- SDK: google-genai 2.9.0. Key supplied by user via env (not stored in the skill).
- Command: segmented mode, voice Sulafat, language cmn-tw, model
  `gemini-3.1-flash-tts-preview`, mp3 output, 2-sentence zh-TW script.
- Result: model accepted; produced real speech (mp3, 24 kHz mono, 8.93 s;
  mean_volume -17.8 dB / max_volume -2.0 dB → not silent). SRT timeline matched the
  measured per-line durations (cue1 0.000→4.680, cue2 4.800→8.880 with the 120 ms gap),
  subtitle text identical to the script.
- Note: the user-requested model `gemini-3.1-flash-tts-preview` works with this account.
  It is not yet listed in the public speech-generation docs (which show the 2.5 TTS
  variants); `--model gemini-2.5-flash-preview-tts` remains the documented fallback.

## Known limitations / residual risk

- Only one paid synthesis path was exercised live; broader voice/language/model matrix
  not exhaustively run (cost control). API request/response handling follows the official
  docs and the one live call.
- `--mode single --align whisper` needs `faster-whisper` (optional); falls back to
  proportional timing when absent. Not exercised live here.
- TTS duration is non-deterministic; fixed-length targets should use `--estimate` then
  confirm the measured `audio_seconds`.
- segmented mode issues one API call per subtitle line; long scripts cost proportionally
  more — preview line count with `--estimate` first.

## Manual review

See `references/checklist_template.md` for non-mechanical review notes.
