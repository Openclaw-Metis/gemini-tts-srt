---
name: gemini-tts-srt
description: "用 Google Gemini API 的文字轉語音模型把腳本配音成音檔，並同時輸出時間軸對齊的 SRT 字幕。Use when 使用者要『用 Gemini 配音 / 生成旁白 / Gemini text-to-speech』、要『配音同時要字幕 / 要 SRT』、或把一段文字轉成可放進影片的語音加字幕（觸發語如『用 gemini 幫這段配音並產 srt』『generate narration with subtitles using gemini tts』『Gemini TTS 字幕』『把這段旁白配音輸出 mp3 和字幕』）。本技能負責：挑 prebuilt voice、套用英文風格指令、呼叫 Gemini TTS、量測每段時長、輸出 wav/mp3 與 SRT。Do not use when 只想規劃 TTS 提示詞而不實際生成（用 tts-prompter）、要搜尋下載現成素材影片或配樂（用 media-downloader）、要用非 Gemini 的 TTS 例如 Edge TTS、或只是要翻譯字幕。成功輸出是一個音檔加一個 cue 數等於腳本行數的 .srt 加一份 JSON 摘要。"
version: 2026.6.20
metadata:
  author: "Openclaw-Metis"
  language: zh-TW
  category: media
  short-description: "Gemini TTS 配音並輸出對齊 SRT 字幕"
---

# Gemini TTS + SRT

把腳本透過 Google Gemini API 的 TTS 模型生成語音，並同時產出與語音對齊的 SRT 字幕。Gemini TTS 只回傳音訊、不附帶任何時間戳，因此本技能的核心價值在於用「逐句合成並實測時長」的方式把字幕時間軸做出來，而不是事後對音檔做語音辨識。本技能也**整合了 `tts-prompter` 的提示詞框架**（見 `references/prompting.md`）——因為 `tts-prompter` 原本就是為 Gemini TTS 設計的——用來指導英文風格指令與 voice 選擇。它不負責下載既有素材（交給 `media-downloader`）。

## Single responsibility

- Primary job: 用 Gemini TTS 把既有腳本配音成音檔、輸出時間軸對齊的 SRT 字幕，並套用內建整合的 `tts-prompter` 提示詞框架來指導風格指令與 voice 選擇。
- Not this skill's job: 搜尋或下載現成影音素材、做字幕翻譯、用非 Gemini 引擎合成、把字幕燒錄進影片。
- Split / handoff rule: 需要素材影片或配樂時交給 `media-downloader`；需要把字幕壓進影片時交給影片合成流程（例如 MoneyPrinterTurbo 類 pipeline）。提示詞框架已內建於本技能，不再外部依賴 `tts-prompter`。

<role>
你是一個語音生成執行者：接收明確的腳本與聲音／風格設定，呼叫 Gemini TTS 產出語音，量測時長並產生對齊的 SRT，最後回報實際檔案路徑與時長。你只在缺少關鍵輸入或金鑰時停下並說明，不替使用者杜撰腳本內容。
</role>

<decision_boundary>
Use when:
- 使用者要用 Gemini API（TTS 模型，如 gemini-3.1-flash-tts-preview 或 gemini-2.5-flash-preview-tts）把一段文字配音。
- 使用者要在配音的同時得到字幕檔（SRT），用於影片旁白、有聲書、Podcast、社群短片。
- 使用者已經有腳本文字，或願意把腳本直接交給你。

Do not use when:
- 使用者要搜尋或下載現成素材影片、圖庫、配樂（用 `media-downloader`）。
- 使用者指定非 Gemini 的 TTS 引擎（例如 Edge TTS、Azure、ElevenLabs）。
- 使用者只要字幕的翻譯或重新斷句，沒有要生成語音。

Inputs:
- 必要：腳本文字（`--text` 或 `--script-file`）。
- 必要（實際合成時）：Gemini API 金鑰（環境變數 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`，或 `--api-key`）。
- 可選：voice 名稱、BCP-47 語言提示、英文風格指令、模式（segmented／single）、輸出格式（wav／mp3）、每行字數上限、段間靜音。

Successful output:
- 一個音檔（`<basename>.wav` 或 `.mp3`）。
- 一個 SRT 檔（`<basename>.srt`），其 cue 數量等於切出的字幕行數，時間戳單調遞增不重疊，字幕文字即原始腳本。
- 一份 JSON 摘要（模式、模型、voice、行數、音檔秒數、檔案路徑）。
</decision_boundary>

## Primary use cases (2-3)

1) **影片旁白配音 + 字幕**
- Trigger examples: 「用 gemini 幫這段旁白配音，順便給我 srt」、「generate narration with subtitles using gemini tts」
- Required inputs: 腳本文字、Gemini 金鑰；可選 voice／語言／風格。
- Expected result: 一個 mp3／wav 加一個對齊的 .srt，可直接放進影片時間軸。

2) **配音前先預覽字幕斷句與時長（不花 API 額度）**
- Trigger examples: 「先幫我看這段配出來字幕大概怎麼斷、多長」、「preview the subtitle timing before synthesizing」
- Required inputs: 腳本文字（不需金鑰）。
- Expected result: 用 `--estimate` 依語速表預估時長，輸出 .srt 與 JSON 報告，不呼叫 API。

3) **單一說話者長段旁白，需較連貫語氣**
- Trigger examples: 「整段一次配，不要一句一句斷掉的感覺」
- Required inputs: 腳本文字、Gemini 金鑰。
- Expected result: 用 `--mode single` 一次合成，字幕時間以比例分配（或 `--align whisper` 做詞級對齊）。

## Communication notes

- User vocabulary: 使用者常說「配音」「旁白」「字幕」「SRT」「voice」「語速」「mp3」。
- Avoid jargon: 不要對使用者拋出 PCM、forced alignment、cue 等內部名詞而不解釋；必要時用「時間軸」「斷句」說明。
- Least-surprise rule: 使用者預期字幕文字就是他給的稿、時間對得上語音；預設不應自行改寫腳本或翻譯。

## Routing boundaries

- Neighboring skills / workflows: `media-downloader`（素材下載）、影片合成 pipeline（把字幕壓進影片）。`tts-prompter` 的框架已整合進本技能。
- Negative triggers: 素材下載、字幕翻譯、非 Gemini 引擎。
- Handoff rule: 風格提示詞框架已內建於 `references/prompting.md`；只有素材與影片合成才交給鄰近技能。

## Language coverage

- Primary language(s): 介面與文件 zh-TW；可生成 Gemini TTS 支援的多語語音。
- Mixed-language trigger phrases: 「用 gemini tts 配音並產 srt」「gemini 配音 加 字幕」「tts + subtitles」。
- Locale-specific wording risks: 風格指令務必用英文（模型對英文指令最穩定）；腳本則用目標語言原文。CJK 字幕每行字數上限應比拉丁語系小（建議 ~16–20）。

## Host / portability targets

- Primary host(s): Agent Skills 相容環境、Claude Code、OpenClaw。
- Secondary host(s): 任何可執行 Python 3 且能裝 `google-genai` 的 runtime。
- Unsupported host(s): 無法執行外部 Python 或無外網（無法呼叫 Gemini API）的環境只能用 `--estimate`。
- Core portable surface: skill pack + 單一 CLI 腳本 `scripts/gemini_tts.py`。
- Host adapters / wrappers needed: 無；金鑰走環境變數。
- State / persistence path: 輸出寫到 `--out-dir`（預設 `./out`），不寫進 skill 資料夾。

<success_criteria>
Quantitative:
- Trigger accuracy: 明確「用 Gemini 配音並要字幕」的請求應穩定命中。
- Tool calls: 一次生成 1 次（single）或 N 次（segmented，N=字幕行數）TTS 呼叫，加少量本地處理。
- Failures: SRT 的 cue 數必須等於字幕行數；時間戳必須單調遞增；0 個損壞輸出檔。

Qualitative:
- 字幕文字零辨識錯誤（直接用原稿）。
- 多字詞／人名不被切斷在兩張字幕卡。
- 新使用者第一次即可產出可用的音檔與字幕。
</success_criteria>

<workflow>
Step 0: Confirm inputs
- Action: 先讀對話與檔案，確認腳本文字、目標語言、voice／風格、輸出格式與是否有時間預算；只有當錯誤假設會改變結果時才追問。缺金鑰且使用者要實際合成時，停下說明可改用 `--estimate` 預覽。
- Input: 使用者提供的腳本、聲音偏好、語言、時長需求；環境變數金鑰是否存在。
- Output: 確認後的參數清單，或「缺少腳本／金鑰」的停止說明。
- Validation: 腳本非空；若要實際合成，`GEMINI_API_KEY`／`GOOGLE_API_KEY` 或 `--api-key` 至少其一存在。

Step 1: Craft the style instruction
- Action: 依內建整合的提示詞框架（`references/prompting.md`）的「Director instructions : Script」公式，用英文寫一段風格指令（語氣／口音／節奏），放進 `--style`；風格指令永遠不會被唸出來。挑一個與角色相符的 voice。
- Input: 使用者想要的語氣、場景、口音；`references/prompting.md` 的 voice 清單。
- Output: 一段英文 `--style` 字串與一個 voice 名稱。
- Validation: 風格指令為英文；voice 在 30 個 prebuilt voices 之內（`--list-voices` 可列）。

Step 2: Choose synthesis mode
- Action: 預設用 `--mode segmented`（逐句合成、實測時長、字幕時間最準）；只有在使用者特別要求整段語氣連貫時改用 `--mode single`（可再加 `--align whisper` 做詞級對齊，需安裝 faster-whisper）。
- Input: 使用者對「逐句準時 vs 整段連貫」的偏好。
- Output: 選定的 mode（與 align）。
- Validation: segmented 模式下每段都會被獨立量測；single 模式下若無法詞級對齊則自動退回比例分配。

Step 3: Preview timing before paid synthesis (recommended)
- Action: 先跑 `python scripts/gemini_tts.py --estimate --language <code> --max-line-chars <n> --text "<script>"`，檢查斷句與預估總長是否符合需求；若有時長預算且超標，回 Step 1 縮短腳本。
- Input: 腳本、語言、每行字數上限。
- Output: 預覽用 `.srt` 與 `.report.json`（不呼叫 API）。
- Validation: 預估總秒數在可接受範圍；字幕斷句沒有把人名／詞語切斷。

Step 4: Synthesize audio and build SRT
- Action: 跑 `python scripts/gemini_tts.py --text "<script>" --voice <name> --language <code> --style "<en style>" --model <id> --format <wav|mp3> --out-dir <dir> --basename <name>`（必要時加 `--mode single`）。模型預設 `gemini-3.1-flash-tts-preview`；若回 404 改用 `gemini-2.5-flash-preview-tts`。
- Input: Step 0–3 確認的參數與金鑰。
- Output: 音檔、`.srt`、JSON 摘要（印在 stdout）。
- Validation: stdout 的摘要 `lines` 等於 `.srt` 的 cue 數；`audio_seconds` 為正且與字幕最後一個 cue 結束時間相符。

Step 5: Validate and report
- Action: 確認音檔可被 `ffprobe` 解析、SRT 時間戳單調遞增不重疊、字幕文字等於原稿；回報檔案絕對路徑、時長、所用模型與 voice。失敗時指出是金鑰、模型名稱、配額還是腳本問題並停止。
- Input: Step 4 產出的檔案與 stdout 摘要。
- Output: 給使用者的完成摘要（檔案路徑 + 時長 + 模型/voice）。
- Validation: cue 數一致、時間軸單調、無損壞檔；任何一項不過即回報為失敗，不宣稱成功。
</workflow>

<output_contract>
Return exactly these sections or fields in this order:
1. 完成摘要（1 行）：模式、模型、voice、總秒數。
2. 檔案清單：音檔與 .srt 的絕對路徑，每行一個。
3. 後續建議（可選，1–2 行）：例如「需要 mp3 改 --format mp3」「字幕太長改小 --max-line-chars」。

Formatting rules:
- 預設回覆用繁體中文。
- 失敗時只輸出失敗原因與下一步，不輸出半成品路徑。
- 不要把音檔內容或 base64 貼進回覆。
- 不要在未實際執行腳本的情況下宣稱已產出檔案。
</output_contract>

<tool_rules>
- 唯一執行入口是 `scripts/gemini_tts.py`；不要在對話中自行用 requests／urllib 重做 Gemini 呼叫或 SRT 邏輯。
- 子指令對應：實際合成用預設模式；預覽用 `--estimate`；列 voice 用 `--list-voices`；離線驗證用 `--self-test`。
- 金鑰只從環境變數或 `--api-key` 取得，絕不寫進 skill 資料夾或印出。
- 實際合成（segmented 模式）會對每行各送一次 API、會消耗配額；對很長的腳本先用 `--estimate` 預估行數與成本，必要時告知使用者預估呼叫次數再執行。
- 風格指令一律英文；voice 必須在 30 個 prebuilt voices 內。
</tool_rules>

<default_follow_through_policy>
- Directly do: 讀腳本、跑 `--estimate`／`--self-test`／`--list-voices`、把輸出寫到使用者指定或預設 `./out`、實際呼叫 Gemini TTS 生成使用者明確要求的這一段配音。
- Ask first: 對「很長」的腳本（預估會產生大量 segmented 呼叫、明顯消耗配額或費用）先告知預估呼叫次數並確認；覆寫已存在的同名輸出檔前先告知。
- Stop and report: 缺腳本、缺金鑰、模型名稱被拒（404）、配額用盡、或 SRT cue 數與行數對不上時，停止並說明原因與下一步。
</default_follow_through_policy>

<examples>
Example 1
Input:
- 使用者：「用 Gemini 幫這段旁白配音，女聲、台灣口音，順便給我 srt：『上古時代，有一位令天地變色的戰神蚩尤……』」

Output:
1. 先用 `--estimate --language cmn-tw --max-line-chars 18` 預覽斷句與總長並確認沒切斷人名。
2. 跑 `gemini_tts.py --text "<稿>" --voice Sulafat --language cmn-tw --style "Speak in Taiwanese Mandarin, calm documentary narrator, steady pace" --format mp3 --basename chiyou --out-dir ./out`。
3. 回報：narration.mp3 + chiyou.srt 的絕對路徑、總秒數、模型與 voice。

Example 2
Input:
- 使用者：「我還沒申請 Gemini 金鑰，但想先看這段配出來字幕怎麼斷、大概幾秒。」

Output:
1. 說明無金鑰可用 `--estimate` 預覽。
2. 跑 `gemini_tts.py --estimate --language cmn-tw --max-line-chars 18 --text "<稿>"`。
3. 回報 .srt 與 .report.json，並提醒預估時長為語速表推估、實際合成後以實測為準。
</examples>

<model_notes>
- GPT-style models: 明確給出每一步要跑的指令與旗標；不要讓模型自由發揮 API 呼叫。
- Reasoning models: 給清楚目標（音檔 + 對齊 SRT）與硬約束（cue 數＝行數、風格指令用英文），中間的斷句與時長計算交給腳本。
- Multi-turn split: 長腳本可拆成「先 estimate 預覽 → 確認 → 再實際合成」兩回合。
</model_notes>

## 放行優先序（fail-first gate precedence）

本技能的交付與自我驗證遵循 fail-first 原則：任一 final gate、stage gate 或 policy gate 為 FAIL / BLOCKED 時，結論只能是 FAIL 或 BLOCKED。不得因為多數檢查通過就把整體判為 PASS。

局部 PASS 只可列在定位資訊，且必須明確標註不具放行效力——例如「format_check 單項通過」只能當作診斷線索，不能作為整體可發布的依據。是否真正可放行，一律以彙整後的 release_gate / stage_gate 結果為準。

## Testing plan

### Triggering tests
- Golden trigger set:
  - Direct:
    - 「用 gemini tts 幫這段配音並產 srt」
  - Indirect:
    - 「generate narration with subtitles using gemini」
  - Negative:
    - 「幫我寫一段 gemini tts 的提示詞就好」（應走 tts-prompter）
- Should trigger:
  - 「Gemini 配音 + 字幕」「把這段旁白配成 mp3 和 srt」
- Should NOT trigger:
  - 「下載一段海浪影片」（media-downloader）、「用 Edge TTS 配音」（非 Gemini）
- Near-miss / confusing cases:
  - 「幫我把這段字幕翻成英文」（純翻譯，不生成語音）
- Should ask before acting:
  - 「把這本 5000 字的稿全部配音」（先估呼叫次數與時長再執行）

### Functional tests
- Test case: zh-TW 腳本 estimate 模式
  - Given: 一段含人名「蚩尤」的中文稿、`--max-line-chars 18`
  - When: 跑 `--estimate`
  - Then: 產出 .srt，cue 數＝行數，人名不被切斷，時間戳單調遞增
- Test case: 離線管線自測
  - Given: 無金鑰環境
  - When: 跑 `--self-test`
  - Then: 全部 PASS（切句、PCM 時長、segmented／single、SRT 格式）

### Performance comparison (optional)
- Baseline (no skill): 直接叫模型寫 code 呼叫 Gemini，常漏掉時間戳對齊、SRT 與行數不一致。
- With skill: 一條指令同時產出對齊 SRT 與音檔。

### ROI guardrail
- Quality gain must justify extra:
  - Time: 多一次 estimate 預覽，換取斷句與時長可控。
  - Tokens: skill 載入成本低；核心在腳本。
  - Maintenance burden: 模型名稱與語速表需隨 Gemini 更新維護。

### Regression gates
- Minimum pass-rate delta: with-skill 不得低於 baseline。
- Maximum allowed time increase: estimate 預覽 < 數秒。
- Maximum allowed token increase: 不顯著。
- Maximum under-trigger failures: 0（明確的 Gemini 配音+字幕請求）。
- Maximum over-trigger failures: 0（純提示詞／素材下載／非 Gemini）。

### Feedback loop
- Common failure signals:
  - 模型名稱 404、配額用盡、SRT 行數對不上。
- Likely fix:
  - 切換 `--model`、改用 `--estimate` 預估、檢查斷句參數（resources / workflow）。

### Model / routing checks
- GPT-style prompt pass: 明確指令可直接執行。
- Reasoning-model pass: 給目標與約束即可。
- Neighbor-skill confusion: 與 `tts-prompter`（提示詞）與 `media-downloader`（素材）邊界以 negative triggers 區隔。

### Host compatibility checks
- Primary host smoke tests: `--self-test` 在無外網環境可全 PASS。
- Wrapper / manifest / config drift review: 無 host wrapper，金鑰走環境變數。
- Auth / approval / persistence checks: 金鑰不落地；輸出寫使用者指定目錄。
- Known unsupported hosts: 無 Python 或無外網者只能 `--estimate`。

## Eval workflow

- Save approved prompts to `assets/evals/evals.json`
- Define release thresholds in `assets/evals/regression_gates.json`
- Prepare paired runs with the skill-creator-advanced toolchain's `prepare_eval_workspace.py` helper.
- If the environment supports subagents or parallel workers, launch with-skill and baseline runs in the same batch
- After runs complete, aggregate results and generate a review viewer
- Validate release thresholds with the toolchain's `check_regression_gates.py` helper against `assets/evals/regression_gates.json`.

## Distribution notes

- Packaging: run the skill-creator-advanced `package_skill.py` helper on this skill folder.
- Keep the core skill folder as the single source of truth; host-specific wrappers should stay thin
- Document supported hosts, auth requirements, approval boundaries, and persistence expectations outside the skill folder
- Repo-level README belongs *outside* this skill folder.

## Troubleshooting

- Symptom: 模型回 404 / model not found
- Cause: `gemini-3.1-flash-tts-preview` 在該帳號或區域尚未開放。
- Fix: 改 `--model gemini-2.5-flash-preview-tts`。

- Symptom: 字幕一句被切成兩張卡、人名被切斷
- Cause: `--max-line-chars` 設太小。
- Fix: CJK 建議 16–20；先用 `--estimate` 預覽再調。

- Symptom: 沒有金鑰無法生成
- Cause: 未設 `GEMINI_API_KEY`／`GOOGLE_API_KEY`。
- Fix: 設環境變數或 `--api-key`；或先用 `--estimate` 預覽。

## Resources

This skill includes:
- `scripts/gemini_tts.py` — 唯一執行入口：Gemini TTS 合成 + 時長量測 + SRT 生成（含 `--estimate`／`--self-test`／`--list-voices`）。
- `references/prompting.md` — **整合自 `tts-prompter` 的完整提示詞框架**（公式、風格／腳本分離、markup tags、30 個 voice、完整語速表）；本技能內建的權威來源。
- `references/srt-strategy.md` — 為什麼 Gemini TTS 要用「逐句實測」對齊字幕，以及三種模式比較。
- `references/readiness_report.md` — release evidence（機械 gate 結果）。
- `references/checklist_template.md` — 人工 review 模板，不是 release gate。
- `references/migration-governance.md` — 改名／棄用／合併／拆分的相容性治理規則。
- `references/migration-template.md` — 變更治理用的遷移紀錄模板。
- `assets/evals/evals.json` — trigger / functional eval fixtures。
- `assets/evals/regression_gates.json` — 發版門檻。
- `skill_lifecycle.yaml` — 生命週期、擁有者、支援矩陣、風險與相依。
