# Readiness report - gemini-tts-srt

Skill version: 2026.6.21
Audit date: 2026-06-21
Owner: Openclaw-Metis
Status: draft (release-hardening revision; paired A/B benchmark still not run)

## Summary

`gemini-tts-srt` turns a script into Gemini TTS narration plus a time-aligned SRT whose
text is the original script. This revision closes the highest-priority gap between the
skill contract and executor guarantees: API errors are classified, retryable Gemini
server errors are retried, unknown voices fail fast, outputs are validated, report files
are always written, output paths are absolute, and long segmented jobs are preflighted
before paid synthesis.

The 2026-06-21 incident-driven revision adds quota-aware mode selection guidance:
segmented mode is no longer treated as a safe default for long or free-tier jobs. When
`estimated_api_calls` is high or quota is unknown, the workflow now prefers `--mode
single`; segmented 429 / `RESOURCE_EXHAUSTED` reports include a fallback hint to stop
per-line retries and rerun single-mode, optionally with the 2.5 TTS fallback model.

## Current Gemini evidence

Source checked: Google AI for Developers, "Text-to-speech generation (TTS)",
last updated 2026-06-18 UTC.

- Default model remains `gemini-3.1-flash-tts-preview`.
- Documented fallback: `gemini-2.5-flash-preview-tts` (and users may also choose other
  Gemini TTS preview variants available to their account).
- The public docs now list Gemini 3.1 Flash TTS Preview for single-speaker and
  multi-speaker examples; the old statement that 3.1 was absent from public speech
  generation docs has been removed.
- TTS has a 32k-token context limit, Gemini 3.1 Flash TTS Preview may drift on outputs
  longer than a few minutes, and the docs recommend automated retry for occasional 500
  errors caused by text-token returns.

## Executor hardening completed

| Area | Evidence |
|---|---|
| API errors | `classify_api_error()` maps 401/403, 404, 429, 500/502/503/504, content rejection, missing key, and missing SDK into non-stack-trace reports. |
| Retry | `synthesize(..., retries=N)` retries retryable 5xx errors with bounded exponential backoff. |
| Voice gate | Unknown voice returns non-zero before any API call and points to `--list-voices`. |
| Output validation | `validate_outputs()` checks cue count, monotonic timing, unchanged text, positive PCM duration, SRT existence, and parseable WAV/MP3. |
| Absolute paths | `--out-dir` is resolved; report JSON contains absolute `audio`, `srt`, and `report` paths. |
| Report file | Estimate, dry-run, success, long-job blocked, API failure, conversion failure, and validation failure paths write `<basename>.report.json`; argparse/input-shape errors may stop before artifact paths are meaningful. |
| Cost preflight | `--max-api-calls` blocks large segmented synthesis unless `--force` is supplied; `--dry-run-cost` reports estimated calls/chunks without API usage. |
| Rate-limit recovery | 429 / `RESOURCE_EXHAUSTED` returns `quota_or_rate_limit`; segmented failures add `fallback.rerun_flags` for `--mode single` and, when appropriate, `--model gemini-2.5-flash-preview-tts`. |
| API key precedence | When both `GEMINI_API_KEY` and `GOOGLE_API_KEY` are set, the CLI warns once and uses `GEMINI_API_KEY`; `--api-key` remains the per-run override. |
| Format contract | `--strict-format` turns MP3 fallback into a non-zero exit for pipelines. |
| Path safety | `--basename` is sanitized and outputs are constrained to `--out-dir`. |
| Protected terms | `--protect-terms` / `--protect-file` prevent critical terms from being split by the line wrapper. |
| Dependencies | `requirements.txt` declares `google-genai>=2.9.0`; `faster-whisper` and ffmpeg remain optional. |

## Local verification

Run from `C:\Users\Oberon\.codex\skills\gemini-tts-srt`.

| Check | Result |
|---|---|
| `python -m py_compile scripts/gemini_tts.py` | PASS |
| `python scripts/gemini_tts.py --self-test` | PASS (`RESULT: ALL PASS`) |
| `python -m json.tool assets/evals/evals.json` | PASS |
| dual-key precedence smoke | PASS; chose `GEMINI_API_KEY` and warned once |
| 429 fallback hint smoke | PASS; classified `quota_or_rate_limit` and produced single-mode rerun flags |
| estimate with sanitized `--basename '..\bad/name'` | PASS; output paths stayed under `--out-dir` and were absolute |
| invalid voice smoke | PASS; command returned non-zero before API use |
| long segmented preflight smoke | PASS; command returned blocked report before API use |

## Common Error Checks

The hardening smoke tests cover the common errors most likely to break first use:
missing/invalid voice, unsafe basename, excessive segmented API calls, missing ffmpeg in
strict MP3 mode, and artifact validation failures. API-only cases that require live
Gemini failures (401/403, 404, 429, 5xx) are covered by deterministic classification
logic and eval fixtures, but were not live-triggered in this pass to avoid unnecessary
paid calls.

## Mechanical gate evidence

Run from `C:\Users\Oberon\.codex\project` against target
`C:\Users\Oberon\.codex\skills\gemini-tts-srt`.

| Gate | Result |
|---|---|
| `release_gate.py <skill> --stage draft --json` | PASS |
| `stage_gate.py <skill> --stage revise --json` | PASS |

Audit-level results from the final run:

| Audit | Result |
|---|---|
| format | PASS |
| structure | PASS |
| workflow_contract | PASS |
| semantics | PASS |
| semantic_rules | PASS |
| gate_language | PASS |
| lifecycle | PASS |
| lifecycle_state | PASS (state: draft) |
| eval_coverage | PASS |
| eval_quality | PASS |
| golden_trigger_set | PASS |
| wrapper_drift | PASS |
| migration_governance | PASS |
| surface_drift | PASS |
| skill_references | PASS |
| unreferenced_files | PASS |
| healthcheck | PASS |
| benchmark | SKIPPED (no paired A/B benchmark artifact supplied) |

Final gate status for this revision: PASS for draft/revise readiness. This does not
promote the skill to beta because live paid synthesis and paired benchmark evidence were
not rerun in this pass.

## Known limitations / residual risk

- Live paid synthesis was not rerun in this hardening pass; API behavior is based on the
  previous live verification plus current public docs.
- Multi-speaker and streaming are documented as future extensions, not implemented in
  this CLI revision.
- `--mode single --align whisper` still needs optional `faster-whisper`; it falls back
  to proportional timing when absent.
- Paired with-skill/baseline benchmark remains not run, so status stays `draft` rather
  than beta.

## Manual review

See `references/checklist_template.md` for non-mechanical review notes. Manual review
does not override release/stage gate failures.
