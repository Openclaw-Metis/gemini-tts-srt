#!/usr/bin/env python3
"""
gemini_tts.py - Gemini TTS voiceover + SRT subtitle generator.

Single execution path for the `gemini-tts-srt` skill. Turns a script into:
  1. an audio file (wav/mp3) spoken by a Gemini prebuilt voice, and
  2. a time-aligned SRT subtitle whose text is the original script (zero ASR error).

WHY THIS DESIGN
---------------
The Gemini TTS API returns ONLY audio (24kHz/16-bit/mono PCM). Unlike Edge TTS it
emits no word/sentence timestamps. So subtitle timing must be derived, not read.

  * mode=segmented (default, recommended): synthesize each subtitle line as its own
    TTS call, then measure that line's real duration directly from the PCM byte count
    (bytes / (rate*sample_width*channels)). Concatenate the segments; the SRT timeline
    is the running sum of measured durations. Exact timing, correct text, no ffprobe,
    no ASR. Cost: one API call per line.

  * mode=single: one TTS call for the whole script (smoother prosody). Timing is then
    either proportional (split total measured duration by per-line unit length) or, if
    --align whisper is set and faster-whisper is installed, word-level forced timing
    re-chunked against the script lines.

  * --estimate: no API call at all. Predict per-line durations from the empirical
    speech-rate table and emit the SRT (+ a JSON report) only. Use it to preview
    subtitle segmentation/timing before spending TTS quota. Also the offline test path.

The TTS model id is configurable (--model). Default is the model requested for this
skill; the official docs currently list the 2.5 TTS variants, so if the default 404s,
pass --model gemini-2.5-flash-preview-tts.

API shape follows https://ai.google.dev/gemini-api/docs/speech-generation
Prompt crafting (style:script formula, voice catalog) follows the tts-prompter skill;
see references/prompting.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------------------
# Audio constants (per Gemini TTS docs: 24kHz, 16-bit signed LE, mono PCM)
# ---------------------------------------------------------------------------
DEFAULT_RATE = 24000
SAMPLE_WIDTH = 2  # bytes (16-bit)
CHANNELS = 1
DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"

# The 30 prebuilt Gemini voices (name -> timbre). Canonical list in references/prompting.md.
VOICES = {
    "Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative", "Kore": "Firm",
    "Fenrir": "Excitable", "Leda": "Youthful", "Orus": "Firm", "Aoede": "Breezy",
    "Callirrhoe": "Easy-going", "Autonoe": "Bright", "Enceladus": "Breathy",
    "Iapetus": "Clear", "Umbriel": "Easy-going", "Algieba": "Smooth", "Despina": "Smooth",
    "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm", "Schedar": "Even",
    "Gacrux": "Mature", "Pulcherrima": "Forward", "Achird": "Friendly",
    "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle", "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}

# Empirical narration speech rates from the tts-prompter Language Catalog (units/sec).
# unit "chars" for unspaced scripts (CJK/Thai/Lao/Burmese), "words" otherwise.
# Only a working subset is embedded; UNKNOWN languages fall back by script detection.
RATE_TABLE = {
    # Full catalog ported from the integrated tts-prompter Language Catalog.
    # unit "chars" for unspaced scripts (CJK/Thai/Lao/Burmese), "words" otherwise.
    "ar-eg": ("words", 1.3), "bn-bd": ("words", 1.8), "nl-nl": ("words", 2.1),
    "en-in": ("words", 2.2), "en-us": ("words", 2.1), "fr-fr": ("words", 2.2),
    "de-de": ("words", 2.1), "hi-in": ("words", 2.1), "id-id": ("words", 1.6),
    "it-it": ("words", 1.9), "ja-jp": ("chars", 4.2), "ko-kr": ("chars", 3.8),
    "mr-in": ("words", 1.6), "pl-pl": ("words", 1.7), "pt-br": ("words", 1.7),
    "ro-ro": ("words", 1.6), "ru-ru": ("words", 1.5), "es-es": ("words", 1.8),
    "ta-in": ("words", 1.3), "te-in": ("words", 1.3), "th-th": ("chars", 7.2),
    "tr-tr": ("words", 1.6), "uk-ua": ("words", 1.5), "vi-vn": ("words", 2.7),
    "af-za": ("words", 2.0), "sq-al": ("words", 2.1), "am-et": ("words", 1.2),
    "ar-001": ("words", 1.3), "hy-am": ("words", 1.5), "az-az": ("words", 1.6),
    "eu-es": ("words", 1.7), "be-by": ("words", 1.5), "bg-bg": ("words", 1.8),
    "my-mm": ("chars", 11.2), "ca-es": ("words", 2.2), "ceb-ph": ("words", 1.9),
    "cmn-cn": ("chars", 2.8), "cmn-tw": ("chars", 2.7), "hr-hr": ("words", 1.7),
    "cs-cz": ("words", 1.8), "da-dk": ("words", 2.1), "en-au": ("words", 2.2),
    "en-gb": ("words", 2.1), "et-ee": ("words", 1.6), "fil-ph": ("words", 1.7),
    "fi-fi": ("words", 1.2), "fr-ca": ("words", 2.2), "gl-es": ("words", 1.9),
    "ka-ge": ("words", 1.4), "el-gr": ("words", 1.6), "gu-in": ("words", 1.8),
    "ht-ht": ("words", 2.6), "he-il": ("words", 1.5), "hu-hu": ("words", 1.8),
    "is-is": ("words", 1.4), "jv-jv": ("words", 1.7), "kn-in": ("words", 1.2),
    "kok-in": ("words", 1.6), "lo-la": ("chars", 8.2), "la-va": ("words", 1.3),
    "lv-lv": ("words", 1.4), "lt-lt": ("words", 1.4), "lb-lu": ("words", 2.0),
    "mk-mk": ("words", 1.7), "mai-in": ("words", 2.1), "mg-mg": ("words", 1.8),
    "ms-my": ("words", 1.6), "ml-in": ("words", 1.2), "mn-mn": ("words", 1.6),
    "ne-np": ("words", 1.4), "nb-no": ("words", 1.7), "nn-no": ("words", 1.6),
    "or-in": ("words", 1.5), "ps-af": ("words", 2.1), "fa-ir": ("words", 1.5),
    "pt-pt": ("words", 1.6), "pa-in": ("words", 2.3), "sr-rs": ("words", 1.7),
    "sd-in": ("words", 2.1), "si-lk": ("words", 1.6), "sk-sk": ("words", 1.7),
    "sl-si": ("words", 1.6), "es-419": ("words", 1.7), "es-mx": ("words", 1.8),
    "sw-ke": ("words", 1.8), "sv-se": ("words", 1.8), "ur-pk": ("words", 2.2),
    # Bare-language aliases for convenience (fall back targets).
    "zh": ("chars", 2.8), "cmn": ("chars", 2.8), "ja": ("chars", 4.2),
    "ko": ("chars", 3.8), "th": ("chars", 7.2), "my": ("chars", 11.2),
    "lo": ("chars", 8.2), "en": ("words", 2.1), "fr": ("words", 2.2),
    "de": ("words", 2.1), "es": ("words", 1.8), "it": ("words", 1.9),
    "pt": ("words", 1.7), "ru": ("words", 1.5), "hi": ("words", 2.1),
    "id": ("words", 1.6), "vi": ("words", 2.7), "nl": ("words", 2.1),
    "tr": ("words", 1.6), "ar": ("words", 1.3),
}
CJK_RE = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
# Sentence-ending punctuation, CJK + ASCII.
SENT_END = "。！？!?…\n"
SOFT_BREAK = "，,、；;：: "


# ---------------------------------------------------------------------------
# Text -> subtitle lines
# ---------------------------------------------------------------------------
def _split_keep(s: str, delim_set: str) -> list[str]:
    """Split s into chunks; each delimiter char terminates (and stays on) its chunk."""
    chunks, buf = [], ""
    for ch in s:
        buf += ch
        if ch in delim_set:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _char_wrap(s: str, cap: int) -> list[str]:
    """Last resort for a punctuation-less run that exceeds cap.

    Wrap by character count but merge a tiny trailing fragment (<4 chars, e.g. a
    2-char name remainder) back into the previous line so words/names are not
    orphaned across cards.
    """
    out: list[str] = []
    while len(s) > cap:
        out.append(s[:cap])
        s = s[cap:]
    if s:
        if out and len(s) < 4:
            out[-1] += s
        else:
            out.append(s)
    return out


def split_into_lines(text: str, max_line_chars: int = 38) -> list[str]:
    """Split a script into readable subtitle lines.

    Strategy (quality-first):
      1) segment into sentences at sentence-ending punctuation;
      2) within an over-long sentence, break at soft punctuation (comma/、/；/space)
         into clauses and greedily merge clauses up to the cap;
      3) only char-wrap a clause that is itself longer than the cap AND has no inner
         punctuation, avoiding tiny orphan fragments.
    This keeps multi-character words/names (e.g. 蚩尤) intact instead of cutting them
    across two subtitle cards.
    """
    text = re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", (text or "").strip()))
    sentences = [s.strip() for s in _split_keep(text, SENT_END) if s.strip()]

    lines: list[str] = []
    for s in sentences:
        if len(s) <= max_line_chars:
            lines.append(s)
            continue
        clauses = _split_keep(s, SOFT_BREAK)
        cur = ""
        for cl in clauses:
            if not cur:
                cur = cl
            elif len(cur) + len(cl) <= max_line_chars:
                cur += cl
            else:
                lines.extend(_char_wrap(cur.strip(), max_line_chars))
                cur = cl
        if cur.strip():
            lines.extend(_char_wrap(cur.strip(), max_line_chars))
    return [ln for ln in lines if ln]


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------
def pcm_duration_seconds(pcm: bytes, rate: int = DEFAULT_RATE) -> float:
    """Exact duration of raw PCM from its byte count."""
    n_frames = len(pcm) / (SAMPLE_WIDTH * CHANNELS)
    return n_frames / float(rate)


def _unit_count(text: str, unit: str) -> float:
    if unit == "chars":
        return max(1, len(re.sub(r"\s+", "", text)))
    return max(1, len(text.split()))


def _resolve_rate(language: str | None, sample_text: str) -> tuple[str, float]:
    if language:
        key = language.strip().lower()
        if key in RATE_TABLE:
            return RATE_TABLE[key]
        base = key.split("-")[0]
        if base in RATE_TABLE:
            return RATE_TABLE[base]
    # No/unknown language: detect by script.
    if CJK_RE.search(sample_text or ""):
        return RATE_TABLE["cmn"]
    return RATE_TABLE["en"]


def estimate_line_seconds(text: str, language: str | None) -> float:
    unit, rate = _resolve_rate(language, text)
    return _unit_count(text, unit) / rate


# ---------------------------------------------------------------------------
# SRT
# ---------------------------------------------------------------------------
def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str


def build_srt(cues: list[Cue]) -> str:
    out = []
    for c in cues:
        out.append(str(c.index))
        out.append(f"{_ts(c.start)} --> {_ts(c.end)}")
        out.append(c.text)
        out.append("")
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------------------
# Audio writing
# ---------------------------------------------------------------------------
def write_wav(pcm: bytes, path: str, rate: int = DEFAULT_RATE) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return False
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", mp3_path],
        capture_output=True,
    )
    return r.returncode == 0


def silence(ms: int, rate: int = DEFAULT_RATE) -> bytes:
    n_frames = int(rate * ms / 1000)
    return b"\x00" * (n_frames * SAMPLE_WIDTH * CHANNELS)


# ---------------------------------------------------------------------------
# Gemini synthesis (lazy import so non-API paths need no SDK / key)
# ---------------------------------------------------------------------------
def _parse_rate_from_mime(mime: str | None) -> int:
    if mime:
        m = re.search(r"rate=(\d+)", mime)
        if m:
            return int(m.group(1))
    return DEFAULT_RATE


def synthesize(text: str, voice: str, style: str, model: str,
               api_key: str | None) -> tuple[bytes, int]:
    """Call Gemini TTS for a single text. Returns (pcm_bytes, sample_rate)."""
    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "google-genai SDK not installed. Run: pip install google-genai"
        ) from e

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "No API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY), or pass --api-key, "
            "or use --estimate to preview without synthesizing."
        )

    client = genai.Client(api_key=key)
    # tts-prompter formula: "{Director instructions}: {script}". Style stays in English.
    contents = f"{style.strip()}: {text}" if style and style.strip() else text
    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    part = resp.candidates[0].content.parts[0]
    pcm = part.inline_data.data
    if isinstance(pcm, str):  # some transports hand back base64 text
        import base64
        pcm = base64.b64decode(pcm)
    rate = _parse_rate_from_mime(getattr(part.inline_data, "mime_type", None))
    return pcm, rate


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------
def run_segmented(lines, *, voice, style, model, api_key, gap_ms,
                  mock=False, language=None):
    """One TTS call per line; measure each; concatenate; exact SRT timing."""
    combined = bytearray()
    cues: list[Cue] = []
    cursor = 0.0
    rate = DEFAULT_RATE
    for i, line in enumerate(lines, 1):
        if mock:
            dur = estimate_line_seconds(line, language)
            pcm = silence(int(dur * 1000))
        else:
            pcm, rate = synthesize(line, voice, style, model, api_key)
            dur = pcm_duration_seconds(pcm, rate)
        start = cursor
        end = cursor + dur
        cues.append(Cue(i, start, end, line))
        combined += pcm
        if i < len(lines):
            combined += silence(gap_ms, rate)
            cursor = end + gap_ms / 1000.0
        else:
            cursor = end
    return bytes(combined), cues, rate


def run_single(lines, *, voice, style, model, api_key, align,
               mock=False, language=None):
    """One TTS call for the whole script; derive per-line timing."""
    full_text = " ".join(lines)
    if mock:
        rate = DEFAULT_RATE
        total = sum(estimate_line_seconds(ln, language) for ln in lines)
        pcm = silence(int(total * 1000))
    else:
        pcm, rate = synthesize(full_text, voice, style, model, api_key)
        total = pcm_duration_seconds(pcm, rate)

    cues: list[Cue] = []
    if align == "whisper" and not mock:
        cues = _align_with_whisper(pcm, rate, lines)
    if not cues:
        # Proportional split by per-line unit length.
        unit, _ = _resolve_rate(language, full_text)
        weights = [_unit_count(ln, unit) for ln in lines]
        wsum = sum(weights) or 1
        cursor = 0.0
        for i, (ln, w) in enumerate(zip(lines, weights), 1):
            dur = total * (w / wsum)
            cues.append(Cue(i, cursor, cursor + dur, ln))
            cursor += dur
    return pcm, cues, rate


def _align_with_whisper(pcm: bytes, rate: int, lines: list[str]) -> list[Cue]:
    """Optional: word-level timing via faster-whisper, re-chunked to script lines."""
    try:
        import tempfile
        from faster_whisper import WhisperModel
    except Exception:
        sys.stderr.write("[warn] faster-whisper not available; using proportional timing.\n")
        return []
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp = tf.name
        write_wav(pcm, tmp, rate)
        model = WhisperModel(os.environ.get("WHISPER_MODEL", "base"))
        segments, _ = model.transcribe(tmp, word_timestamps=True)
        words = [w for seg in segments for w in (seg.words or [])]
        if not words:
            return []
        # Greedy: accumulate word spans until each script line's char budget is met.
        cues, wi = [], 0
        for idx, line in enumerate(lines, 1):
            budget = len(re.sub(r"\s+", "", line))
            start = words[wi].start if wi < len(words) else 0.0
            got, end = 0, start
            while wi < len(words) and got < budget:
                end = words[wi].end
                got += len(re.sub(r"\s+", "", words[wi].word))
                wi += 1
            cues.append(Cue(idx, start, end, line))
        return cues
    except Exception as e:
        sys.stderr.write(f"[warn] whisper alignment failed ({e}); proportional timing.\n")
        return []


# ---------------------------------------------------------------------------
# Self-test (offline, no API)
# ---------------------------------------------------------------------------
def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    print("self-test: splitting")
    zh = "上古時代，有一位令天地變色的戰神蚩尤。他銅頭鐵額，刀槍不入，還能呼風喚霧。傳說至今仍在山海之間流傳。"
    lines = split_into_lines(zh, max_line_chars=12)
    check("zh splits into >=3 lines", len(lines) >= 3)
    check("no line exceeds cap+slack", all(len(l) <= 16 for l in lines))

    print("self-test: pcm duration math")
    one_sec = silence(1000)
    check("1s silence ~= 1.0s", abs(pcm_duration_seconds(one_sec) - 1.0) < 1e-6)

    print("self-test: segmented pipeline (mock)")
    pcm, cues, rate = run_segmented(lines, voice="Charon", style="", model="x",
                                    api_key=None, gap_ms=100, mock=True, language="cmn-tw")
    check("one cue per line", len(cues) == len(lines))
    check("monotonic non-overlapping", all(
        cues[i].start >= cues[i - 1].end - 1e-9 for i in range(1, len(cues))))
    check("cue text == source line", all(c.text == l for c, l in zip(cues, lines)))
    audio_dur = pcm_duration_seconds(pcm, rate)
    check("audio covers last cue end", audio_dur + 1e-6 >= cues[-1].end - 0.2)

    print("self-test: srt formatting")
    srt = build_srt(cues)
    check("srt has arrow", "-->" in srt)
    check("ts format HH:MM:SS,mmm", bool(re.search(r"\d{2}:\d{2}:\d{2},\d{3}", srt)))
    check("_ts rounds", _ts(3661.5) == "01:01:01,500")

    print("self-test: single mode proportional (mock)")
    pcm2, cues2, _ = run_single(lines, voice="Charon", style="", model="x",
                                api_key=None, align="none", mock=True, language="cmn-tw")
    check("single: one cue per line", len(cues2) == len(lines))
    check("single: covers whole duration", abs(cues2[-1].end - pcm_duration_seconds(pcm2)) < 0.05)

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Gemini TTS voiceover + SRT generator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--text", help="Script text to speak (the words only).")
    src.add_argument("--script-file", help="Path to a UTF-8 text file with the script.")
    p.add_argument("--style", default="",
                   help="Director's notes / style instructions (English). Goes before "
                        "the colon per the tts-prompter formula. NEVER spoken.")
    p.add_argument("--voice", default="Charon",
                   help="Prebuilt Gemini voice name (default: Charon). See --list-voices.")
    p.add_argument("--language", default="",
                   help="BCP-47 hint (e.g. cmn-tw, en-US). Selects regional voice + "
                        "rate-table row; does not force output language.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"TTS model id (default: {DEFAULT_MODEL}). If it 404s, try "
                        "gemini-2.5-flash-preview-tts.")
    p.add_argument("--mode", choices=["segmented", "single"], default="segmented",
                   help="segmented=per-line synth+exact timing (default); "
                        "single=one call + derived timing.")
    p.add_argument("--align", choices=["none", "whisper"], default="none",
                   help="single mode only: word-level timing via faster-whisper if "
                        "installed (default none=proportional).")
    p.add_argument("--out-dir", default="./out", help="Output directory.")
    p.add_argument("--basename", default="narration", help="Output file basename.")
    p.add_argument("--format", choices=["wav", "mp3"], default="wav",
                   help="Audio format (mp3 needs ffmpeg).")
    p.add_argument("--gap-ms", type=int, default=120,
                   help="Silence between segments in segmented mode (default 120ms).")
    p.add_argument("--max-line-chars", type=int, default=38,
                   help="Max characters per subtitle line before wrapping (default 38).")
    p.add_argument("--estimate", action="store_true",
                   help="No API call: predict timing from the rate table, write SRT + "
                        "report only. Preview segmentation before paying for synthesis.")
    p.add_argument("--api-key", default="",
                   help="Gemini API key (else GEMINI_API_KEY / GOOGLE_API_KEY env).")
    p.add_argument("--list-voices", action="store_true", help="List the 30 voices and exit.")
    p.add_argument("--self-test", action="store_true",
                   help="Run offline pipeline self-tests (no API) and exit.")
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.list_voices:
        for name, timbre in VOICES.items():
            print(f"{name:16s} {timbre}")
        return 0

    # Resolve script text.
    if args.script_file:
        with open(args.script_file, encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        p.error("provide --text or --script-file (or --self-test / --list-voices)")
        return 2
    if args.voice not in VOICES:
        sys.stderr.write(f"[warn] '{args.voice}' is not a known prebuilt voice.\n")

    lines = split_into_lines(text, args.max_line_chars)
    if not lines:
        p.error("script produced no subtitle lines")
        return 2

    os.makedirs(args.out_dir, exist_ok=True)
    srt_path = os.path.join(args.out_dir, args.basename + ".srt")
    lang = args.language or None

    # ---- Estimate mode: SRT + report only, no synthesis ----
    if args.estimate:
        cues, cursor = [], 0.0
        for i, ln in enumerate(lines, 1):
            dur = estimate_line_seconds(ln, lang)
            cues.append(Cue(i, cursor, cursor + dur, ln))
            cursor += dur + args.gap_ms / 1000.0
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(build_srt(cues))
        report = {
            "mode": "estimate", "lines": len(lines),
            "estimated_total_seconds": round(cues[-1].end, 2),
            "srt": srt_path, "note": "Durations are rate-table predictions, not measured.",
        }
        rep_path = os.path.join(args.out_dir, args.basename + ".report.json")
        with open(rep_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # ---- Real synthesis ----
    try:
        if args.mode == "segmented":
            pcm, cues, rate = run_segmented(
                lines, voice=args.voice, style=args.style, model=args.model,
                api_key=args.api_key or None, gap_ms=args.gap_ms, language=lang)
        else:
            pcm, cues, rate = run_single(
                lines, voice=args.voice, style=args.style, model=args.model,
                api_key=args.api_key or None, align=args.align, language=lang)
    except RuntimeError as e:
        sys.stderr.write(f"[error] {e}\n")
        return 1

    wav_path = os.path.join(args.out_dir, args.basename + ".wav")
    write_wav(pcm, wav_path, rate)
    audio_path = wav_path
    if args.format == "mp3":
        mp3_path = os.path.join(args.out_dir, args.basename + ".mp3")
        if wav_to_mp3(wav_path, mp3_path):
            audio_path = mp3_path
        else:
            sys.stderr.write("[warn] ffmpeg unavailable; kept WAV.\n")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(build_srt(cues))

    report = {
        "mode": args.mode, "model": args.model, "voice": args.voice,
        "lines": len(lines), "audio": audio_path, "srt": srt_path,
        "audio_seconds": round(pcm_duration_seconds(pcm, rate), 2),
        "sample_rate": rate,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
