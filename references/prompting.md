# Prompt-crafting framework (integrated tts-prompter)

This is the **canonical, integrated** prompt-crafting reference for `gemini-tts-srt`.
The `tts-prompter` framework was designed specifically for Gemini TTS, so it lives here
as a first-class part of this skill — there is no external dependency to defer to. Read
this before writing the `--style` string and choosing a `--voice`.

## 1. The formula

```
{Director instructions in ENGLISH}: {Script in the target language}
```

The single most important rule is to physically separate **how to speak** (Director
instructions) from **what to say** (the Script) with a colon. In this skill:

- The part **before** the colon → pass via `--style`. It is **never spoken**.
- The part **after** the colon → your script (`--text` / `--script-file`). The skill
  builds `"{style}: {line}"` per segment internally, so you provide the two parts
  separately, not pre-joined.

**Alignment rule:** style instructions, the text, and any tags should all point the same
direction. A frightened instruction works best with text that actually sounds alarming.

### Multi-speaker
Gemini TTS supports up to two speakers. For dialogue, the convention is to label each
line with a speaker name; multi-speaker config is a future extension of this skill
(current `scripts/gemini_tts.py` targets single-voice narration + SRT).

## 2. Part 1 — Style instructions (before the colon)

**This part is NEVER spoken.** It is your primary control over the performance.

- **Write it in English**, regardless of the spoken language. The model follows English
  instructions most reliably. (If you name a language here that conflicts with the
  script, the model follows the instruction language — keep them consistent.)
- **State the target language and accent explicitly** here, e.g. "Speak in Taiwanese
  Mandarin…", because the style text carries the highest weight.
- **Mixed-language scripts:** if the script mixes languages (e.g. Japanese with English
  words), say so in the style instructions so the model switches pronunciation rules.
- **Don't over-specify.** Leaving some room often yields more natural delivery.
- **Avoid real brand / real-person identities** ("Chanel-style", "like <celebrity>") —
  the most common trigger of silent policy blocks. Describe the style generically.
- **Avoid sensitive-content cues** (violence, sexual, hate, self-harm, illegal) — soften
  descriptors to avoid silent blocks.

Examples:
- ❌ Weak: `Speak in a scared way: I think someone is in the house.`
- ✅ Strong: `You are hiding in a dark closet. Speak in English with a terrified,
  trembling whisper as if afraid of being caught: I think someone is in the house.`
- Accent: `Speak in Brazilian Portuguese with a standard São Paulo accent: …`
- Mixed: `Speak in a mix of Japanese and English, professional and confident: …`

### Emotion & tone (via instructions, not adjective tags)
- Laugh: `React with an amused, genuine laugh before speaking: Hahaha, I did NOT …`
- Sigh: `You are exhausted. Start with a heavy, tired sigh: Oh man… I can't do this …`

### Pacing & volume
- Pace: `Read this disclaimer extremely fast, like a radio voiceover rushing the terms: …`
- Volume: `You are trying not to wake a sleeping baby. Whisper as quietly as possible: …`

## 3. Part 2 — Spoken text (after the colon)

**This part IS spoken.** Put it in `--text` / `--script-file`.

- **Match the target language exactly.** Want Japanese → write Japanese characters; want
  a JA/EN mix → write the mix. Do not rely on the model to translate on the fly.
- **Punctuation matters.** Commas, periods, semicolons create natural pauses and also
  drive this skill's subtitle segmentation (see `references/srt-strategy.md`).

### Markup tags (inside the script only)
Bracketed tags inject localized, non-spoken actions. There is no fixed list — the model
interprets descriptive words in brackets — but follow these rules:

**DO use tags for** (place inside the script, after the colon):
1. Non-speech sounds: `[sigh]`, `[laughing]`, `[uhm]`, `[cough]`, `[gasp]`
2. Local style shifts: `[shouting]`, `[whispering]`, `[extremely fast]`, `[sarcasm]`, `[asmr]`
3. Pacing/pauses: `[short pause]` (~250ms), `[medium pause]` (~500ms), `[long pause]` (~1s)

**DO NOT use emotional adjective tags** (`[scared]`, `[curious]`, `[bored]`) inside the
script — the engine reads the word aloud, ruining the audio. Put emotion in `--style`.

Golden rule: **tags for precise moments, style instructions for overall tone.**

## 4. Duration vs faithfulness

TTS duration is **not deterministic** — the model picks its own rate; you cannot tightly
control seconds via wording or rate tags.

- **No time limit** (just want audio of the text): ignore duration; optimize for reading
  the text fully and accurately in the requested style.
- **Time-constrained** (fixed video slot, ad spot): use `--estimate` first to predict
  length from the rate table below, trim the script if over budget, then synthesize and
  read the **measured** `audio_seconds` from the JSON summary to confirm the real fit.

## 5. Voice catalog (30 prebuilt voices)

`python scripts/gemini_tts.py --list-voices` prints this. `--language` only hints the
regional model; it does not force the spoken language.

| Voice | Gender | Timbre | | Voice | Gender | Timbre |
|---|---|---|---|---|---|---|
| Zephyr | F | Bright | | Algenib | M | Gravelly |
| Puck | M | Upbeat | | Rasalgethi | M | Informative |
| Charon | M | Informative | | Laomedeia | F | Upbeat |
| Kore | F | Firm | | Achernar | F | Soft |
| Fenrir | M | Excitable | | Alnilam | M | Firm |
| Leda | F | Youthful | | Schedar | M | Even |
| Orus | M | Firm | | Gacrux | F | Mature |
| Aoede | F | Breezy | | Pulcherrima | F | Forward |
| Callirrhoe | F | Easy-going | | Achird | M | Friendly |
| Autonoe | F | Bright | | Zubenelgenubi | M | Casual |
| Enceladus | M | Breathy | | Vindemiatrix | F | Gentle |
| Iapetus | M | Clear | | Sadachbia | M | Lively |
| Umbriel | M | Easy-going | | Sadaltager | M | Knowledgeable |
| Algieba | M | Smooth | | Sulafat | F | Warm |
| Despina | F | Smooth | | Erinome | F | Clear |

## 6. Language catalog (speech-rate table)

`Unit` is `chars` for unspaced scripts (CJK/Thai/Lao/Burmese), `words` otherwise. `Rate`
is units/second for documentary-style narration. Rate varies ~±25% by delivery style;
voice choice affects rate only ~±5%. Used by `--estimate`.

| Language | Code | Unit | Rate | | Language | Code | Unit | Rate |
|---|---|---|---|---|---|---|---|---|
| Arabic (Egypt) | ar-EG | words | 1.3 | | Korean | ko-KR | chars | 3.8 |
| Bangla | bn-BD | words | 1.8 | | Marathi | mr-IN | words | 1.6 |
| Dutch | nl-NL | words | 2.1 | | Polish | pl-PL | words | 1.7 |
| English (India) | en-IN | words | 2.2 | | Portuguese (BR) | pt-BR | words | 1.7 |
| English (US) | en-US | words | 2.1 | | Romanian | ro-RO | words | 1.6 |
| French (FR) | fr-FR | words | 2.2 | | Russian | ru-RU | words | 1.5 |
| German | de-DE | words | 2.1 | | Spanish (ES) | es-ES | words | 1.8 |
| Hindi | hi-IN | words | 2.1 | | Tamil | ta-IN | words | 1.3 |
| Indonesian | id-ID | words | 1.6 | | Telugu | te-IN | words | 1.3 |
| Italian | it-IT | words | 1.9 | | Thai | th-TH | chars | 7.2 |
| Japanese | ja-JP | chars | 4.2 | | Turkish | tr-TR | words | 1.6 |
| Ukrainian | uk-UA | words | 1.5 | | Vietnamese | vi-VN | words | 2.7 |
| Mandarin (CN) | cmn-CN | chars | 2.8 | | Mandarin (TW) | cmn-tw | chars | 2.7 |
| Burmese | my-MM | chars | 11.2 | | Lao | lo-LA | chars | 8.2 |
| English (GB) | en-GB | words | 2.1 | | English (AU) | en-AU | words | 2.2 |
| French (CA) | fr-CA | words | 2.2 | | Portuguese (PT) | pt-PT | words | 1.6 |
| Spanish (MX) | es-MX | words | 1.8 | | Spanish (LatAm) | es-419 | words | 1.7 |

Additional supported codes (rate in `scripts/gemini_tts.py` RATE_TABLE): af-ZA, sq-AL,
am-ET, ar-001, hy-AM, az-AZ, eu-ES, be-BY, bg-BG, ca-ES, ceb-PH, hr-HR, cs-CZ, da-DK,
et-EE, fil-PH, fi-FI, gl-ES, ka-GE, el-GR, gu-IN, ht-HT, he-IL, hu-HU, is-IS, jv-JV,
kn-IN, kok-IN, la-VA, lv-LV, lt-LT, lb-LU, mk-MK, mai-IN, mg-MG, ms-MY, ml-IN, mn-MN,
ne-NP, nb-NO, nn-NO, or-IN, ps-AF, fa-IR, pa-IN, sr-RS, sd-IN, si-LK, sk-SK, sl-SI,
sw-KE, sv-SE, ur-PK. Unknown codes fall back by script detection (CJK → chars, else words).
