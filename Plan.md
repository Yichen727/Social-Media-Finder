# Speaker Extraction and Social Search — Development Plan

Status: milestones 1–3 completed, 3 November 2026. CSV import, ordered main-speaker proposals, and the Speakers review/edit/export workspace are implemented. Social-search handoff remains planned. The supplied CSV/DOCX files are unchanged.

Spreadsheet extension, 4 November 2026: Speakers Detection now accepts CSV and XLSX, with visible worksheet selection for Excel uploads. Review approval and ordered extraction are shared by both formats. Export format is selectable as CSV or XLSX independently of the input format. XLSX export from a workbook patches approved speaker cells in the selected worksheet while retaining the other workbook parts; CSV export covers the selected table. Source files remain unchanged. Added regression cases and static syntax checks; execution is left to the user under the existing testing preference. Earlier verification counts below are historical.

## 1. Confirmed requirements

Deliver two stages:

1. Detect and fill **speaker information** for **all rows with valid numeric Ref Number values**. The supplied sample contains 93 such talks; 93 is not a processing limit. Use the following sources in this exact order:
   1. The row's `High-res video name`.
   2. The same row's `YouTube Caption`.
   3. Opening paragraphs of the matching DOCX in the transcript folder.
2. Transfer a reviewed main speaker's name into the existing social search form. The user chooses platforms and starts the search.

**As soon as a source successfully produces names under its source policy, fill `Speakers` and stop processing that row. Do not analyze lower-priority sources to verify, enrich, or add names after success.** If all three sources fail, leave the blank speaker cell blank.

Updated title policy, confirmed 3 November 2026: `Speakers` can contain all explicitly named title participants, including conversation partners or a title-named host. Preserve their order and join names with `; `. Ref 26 includes both Ai Da and Tim Marlow; Ref 42 is Kader Attia. Caption fallback retains the main-speaker role check. Transcript fallback now collects name candidates regardless of role, including partial names supported by an introduction/address; every transcript candidate is marked with `*` in the preview and export.

Keep the current concise interface and search-index-based social finder. The reverted Playwright experiment is outside this plan. No automatic searches of all imported names are included.

## 2. Findings from the supplied files

Inspected read-only:

- `NEW Culture Summit High Resolution Content with Views and Metrics(Mapped Content).csv`
- `TRANSCRIPTS V2.zip`

| Item | Observed result | Planned handling |
| --- | --- | --- |
| CSV size | 254 data rows, 21 columns | Preserve every original row and column in the completed CSV. |
| Sample numbered talks | 93 rows with unique numeric `Ref Number` values 1–93 | The sample has 93 talks; any valid integer reference is supported, without a fixed 1–93 limit. |
| Out-of-scope rows | 160 blank references and one reference containing `YES` | Leave their speaker values and all other cells unchanged. No title-only processing of these rows. |
| Speaker field | Existing header is `Speakers`, plural | Reuse it rather than adding a duplicate `Speaker` column. |
| Existing values | References 1–4 have speaker text | Retain the previous fill-blanks-only default: preserve those four cells; process the 89 numbered blank cells unless the user explicitly clears an existing value. |
| Caption content | All 93 numbered rows have a caption cell, but 49 contain `No description` | Treat placeholders as unavailable content; the other 44 cells are potential sources, not guaranteed successful detections. |
| Transcripts | 93 numbered DOCX files | Every valid reference has exactly one matching DOCX in this sample. |
| Encoding | UTF-8 decoding failed; Windows-1252 decoding succeeded | Detect CSV settings automatically; retain the detected input encoding and original BOM on export. |
| Damaged text | Some video-title names contain literal `?` | Do not reconstruct missing letters by guessing; continue to the next source. |

DOCX files use descriptive names such as `05. Keynote Conversations_ ...docx`. Also support an explicit numbered parent folder containing `transcript.docx`. Do not assume every file is literally called `transcript.docx`.

These observations describe the input structure. No extraction accuracy rate or completed CSV is claimed.

## 3. Stage 1 — import and strictly ordered extraction

### 3.1 Import and row eligibility

Add a compact `Speakers` workspace with CSV upload, transcript folder path, `Find speakers`, editable preview, and `Download completed CSV`.

- Locate `Ref Number`, `High-res video name`, `YouTube Caption`, and `Speakers` using case/whitespace-tolerant header lookup. Preserve original header spelling/order on export.
- Accept an existing `Speaker` header as an alternative. Add `Speakers` only when neither exists; if both exist, let the user choose the target column.
- Keep cell values as strings to preserve blanks, identifiers, URLs, and leading zeroes. Validate encoding, delimiter, and row structure.
- Only valid numbered talk rows are eligible. Preserve the original source row identity separately from `Ref Number` so rows cannot be merged or overwritten accidentally.
- Preserve existing nonblank speaker cells by default. Existing spelling, aliases, and role text are not silently rewritten.
- Missing/blank source fields are unavailable stages, not permission to invent values or fetch additional data from the web.

The initial release does not fill unnumbered rows, infer a replacement for `YES`, or search outside the three agreed sources. `YouTube title` is not an additional fallback or corroboration source.

### 3.2 Success contract and stopping rule

Each source extractor returns one of four internal outcomes:

| Outcome | Meaning | Next action |
| --- | --- | --- |
| Found | A supported, usable name is attributable to the main speaker | Propose the name in `Speakers` and stop this row immediately. |
| Not found | No main-speaker name was found | Continue to the next source. |
| Ambiguous | Names appear, but the main speaker cannot be established | Continue to the next source; do not fill with the first name or a complete attendee list. |
| Unavailable | Source is blank, a placeholder, missing, or unreadable | Continue to the next source. |

Title success requires complete names explicitly attributed to the talk or conversation. More than one title participant is allowed under the updated policy. Caption success still requires main-speaker evidence. Transcript success collects supported name mentions, including people merely mentioned, and requires manual review via `*`; it does not invent a full identity from a partial name. Institutions and generic topic text are filtered where the rules recognize them.

Explicitly named title participants are now a confirmed exception to the original single-main-speaker policy. A title can end processing with several names. Caption participant lists without an identifiable main role remain unresolved. Transcript name lists are now allowed regardless of role and are marked for review rather than reduced to the first panelist.

The CSV is parsed once, so its caption text may already be in memory. Early stopping means the caption extractor is not called after a title succeeds, and the transcript is not indexed/read for that row after either earlier source succeeds.

### 3.3 Detection 1: High-res video name

Analyze only the current row's `High-res video name`, using a temporary normalized copy. Preserve the original title cell.

Consider strong formats such as `Keynote by [name]`, `Artist Talk: [name]`, and clearly person-named talks. Recognize Unicode names, accents, initials, apostrophes, hyphens, long Arabic names, honorifics, and explicit professional mononyms.

Recognize explicit multi-person title formats with `&`, `and`, `with`, and `in conversation with`, including a conversation attribution after an initial topic. Preserve name hyphens while excluding trailing topics and video extensions. Recognize a named owner in `[Name]'s Liner Notes`. Do not treat generic capitalized topics or organizations as people. Successful multiple names use `Name One; Name Two` in the CSV and retain individual names via `Detection.names`.

An institution-only title such as `A case study by Louvre Abu Dhabi`, damaged text such as `Andra?s Sza?nto?`, or unresolved role ambiguity proceeds to **YouTube Caption**, not directly to the transcript.

If successful, set the proposed speaker and record title evidence. Do not run caption or transcript extraction afterward.

### 3.4 Detection 2: YouTube Caption

Run only when title detection did not succeed. Read the existing CSV cell; do not request the YouTube URL, download subtitles, or call a caption API.

- Normalize whitespace for analysis while retaining the original cell value.
- Treat `No description` and equivalent empty placeholders as unavailable.
- Identify explicit attribution such as `Keynote by`, `Main speaker`, a clearly featured speaker, or a description assigning the talk to a named person.
- Distinguish `Moderated by` from the main-speaker role. A `Speakers:` list containing several panelists does not, by itself, identify one main speaker.
- Ignore channel boilerplate, organizations, promotional links, acknowledgments, and unrelated names.
- If text is damaged or the main role remains uncertain, continue to the transcript.

On success, fill the proposed speaker and keep a short evidence excerpt from `YouTube Caption`. Do not open the DOCX or perform transcript analysis afterward.

### 3.5 Detection 3: matching transcript paragraphs

Run only when both CSV sources failed to establish the main speaker. Lazily index the selected transcript folder on the first row that needs this stage; cache that index for later fallback rows.

Match exact normalized numeric references: CSV `5` matches a `05.` filename prefix. For a generic `transcript.docx`, use an unambiguous numbered parent folder. Do not match `1` to `10`, use directory order, or assume a CSV row number is the reference.

Missing/unreadable documents, conflicting file/folder references, and duplicate matches remain unresolved for review. Do not silently choose a file.

Read DOCX text locally, preserving paragraph order and joining text runs. Standard-library ZIP/XML parsing is sufficient for the structure inspected so far. The first paragraph may be a title and the first spoken turn may only say `Hello`; examine opening spoken turns instead of taking the first paragraph/name mechanically.

Proposed initial bounds are the first three minutes of timestamped speech and at most 8,000 characters; use a bounded paragraph window if timestamps are absent. Tune these limits against the actual sample.

Collect name candidates throughout the bounded opening rather than requiring a main-speaker role. Include introductions, moderators, panelists, acknowledgments, quotations, and other mentioned people. Recognize Unicode names, initials, and cue-backed partial names; retain the supplied spelling and never invent a missing surname. Diarization labels such as `Speaker 78` are not names.

Deduplicate exact normalized mentions in first-appearance order. Preserve individual source paragraphs/timestamps and keep undecorated names in `Detection.names`. Set `requires_review=True`; serialize each candidate as `Name*` when populating the table or CSV. Existing uploaded values and successful title/caption names receive no automatic marker.

Show one marker legend and evidence on demand. Users can edit or remove candidates and remove `*` after checking. Approval does not silently remove markers. No supported candidates means blank; no fourth source, cross-document identity completion, external search, or model-memory lookup follows. These remain lexical candidates: locations, works, and organizations can be misclassified, and the opening window may miss people. Do not report the number of nonblank rows as extraction accuracy.

### 3.6 Examples from the supplied material

| Example | Behavior under the confirmed rules |
| --- | --- |
| Clear `Keynote by [name]` in the video title | Fill the main speaker from the title; skip caption and transcript extraction. |
| Title has no usable name; caption explicitly identifies the main speaker | Fill from the caption; do not open the transcript. |
| Ref 5: damaged title name; caption is `No description`; transcript has Alexandra Munroe introducing András Szántó as the person giving the talk | Collect both Alexandra Munroe and András Szántó as marked transcript candidates; do not claim that both are main speakers. |
| Ref 18: institution-only title; caption is `No description`; transcript starts with Manuel Rabaté presenting the Louvre Abu Dhabi case study | Reject the institution as a person; collect Manuel Rabaté and any other recognized name mentions in the opening, with `*`. |
| Ref 27: caption says `Moderated by Alexandra Munroe` and lists four people under `Speakers:` | Caption does not select a main speaker. Continue to transcript and collect recognized mentions, including Alexandra and panelists, each marked with `*`. |
| Ref 9: title explicitly names Christopher Kulendran Thomas with X Zhu-Nowell | Retain both title names in order and stop; no transcript spelling correction or external identity completion. |
| Ref 32: caption does not establish a main speaker; transcript welcomes only `Alexandra` and thanks `Mohammed` | Keep supported partial names as `Alexandra*` and `Mohammed*`; do not invent surnames. |

### 3.7 Review and completed CSV

The **Need Review** checkbox filters the editable preview to rows whose current `Speakers` value is blank/whitespace or contains `*`. It defaults off, preserves edits by source row ID, and never changes the export scope. Completed rows disappear from the filtered view after editing. Milestone 4 handoff is deferred at the user’s request; this update adds only the review filter. No tests were run for this update.

Keep the preview concise: `Ref Number`, `High-res video name`, and editable `Speakers`. Show the winning source and supporting excerpt for a selected row on demand. Do not add visible confidence scores or repeated warning banners.

Keep original and proposed values separate; allow edits and clearing proposals. Do not discard user edits when rerunning the same upload without an explicit reset.

Export a new `<original-name>_speakers_filled.csv` with all 254 original rows and 21 original columns for this sample. Change only approved speaker cells among the 93 eligible numbered rows. Preserve the four prefilled values by default and all 161 out-of-scope rows. Preserve source business columns, including the source CSV's `Match status`, independently of the social table's display policy. Do not overwrite the original CSV or DOCX files.

## 4. LLM position

The existing recommendation remains **rules first, optional LLM assistance for difficult cases**. This is not yet a confirmed requirement to use a model.

An optional LLM would help interpret names and main-speaker roles within the currently active source. It must obey the same three-step cascade:

- Title success ends processing, including any later model work on captions/transcripts.
- Caption analysis receives the current row's caption, not a combined transcript request.
- Transcript analysis is allowed only when both earlier stages have failed.
- Return structured names, roles, evidence quotations, and source locations; reject unsupported names or a main-speaker claim without supporting evidence.
- Do not let source text become application instructions, invoke tools/web searches, or supply surnames from model memory.

No LLM stage may read lower-priority sources after success, introduce `YouTube title` as a hidden fourth source, or guess identities. Any future transcript adapter must follow the current all-mentions/candidate-marker policy. Invalid or inconclusive model output is a failed extraction and proceeds to the next permitted source, or stays blank after the transcript.

The rule-only path should work without an API key. Provider choice, credentials, external processing, cost, and latency remain discussion items only if optional model assistance is adopted. No model calls are made during planning.

## 5. Stage 2 — reviewed main speaker to social search

- Select an eligible talk, then one reviewed name if its title provided multiple participants.
- Use `Use in social search` to prefill the existing Full Name field.
- Keep the user's platform selection and require an explicit `Search` click.
- Preserve LinkedIn-only profession/company inputs and extraction; Instagram and X remain focused on names, followers, and reference links.
- Preserve follower sorting, social CSV export, and the current concise interface.

Keep individual reviewed speaker records separately from the CSV cell, with source row, reference, accepted name, winning source, and evidence. Existing cells may include aliases, job titles, or organizations; do not pass the entire cell blindly into the search name or split it automatically on commas.

Group exact normalized duplicate names only for search convenience while retaining every source reference; do not assume that same-name people are the same identity or merge fuzzy spellings. Preserve meaningful name particles such as `bin` and `Al`. Transcript affiliations must not be copied into social profile facts. Transfer the reviewed name only.

Automatic batch searching, background search queues, and searches for moderators/guests are outside this release.

## 6. Implementation sequence

Reference-scope correction: CSV import and transcript matching accept all valid nonnegative integer references, without a fixed 1–93 range or nine-digit application limit. Blank/non-numeric references remain excluded, and duplicate-reference handling is unchanged. The UI derives transcript matching scope from the current CSV. No tests were run for this update, per the user’s preference.

UI update: Speakers Detection is the first/default workspace. CSV options are hidden and fixed to Auto; exports preserve the detected source encoding and BOM. This small update was not tested, as requested by the user. Earlier verification counts below describe previous versions.

Transcript-policy update: collect opening name mentions regardless of main-speaker role, preserve per-name evidence, and mark each transcript candidate with `*` in preview/export. The corrected-file run produced 38 title rows and 48 transcript-candidate rows, with three unresolved; these are not verified-speaker counts. All 178 focused tests passed. See [validation/transcript-candidates.md](validation/transcript-candidates.md), including known false positives and limits.

Title-rule update: all nine user feedback cases pass on the corrected UTF-8 CSV, including both participants in Ref 26. Title successes on its 89 pending rows increased from 27 to 38 under the revised policy; total proposals are 39, with 50 unresolved. All 162 focused tests passed. See [validation/speaker-titles.md](validation/speaker-titles.md). Earlier milestone counts below are historical runs.

Milestone 1 is implemented and verified: 36 focused tests passed; the supplied data preserved 254 rows/21 columns, identified 93 eligible talks (89 pending, four prefilled), and matched all 93 DOCX files without reading their bodies. See [validation/speaker-import.md](validation/speaker-import.md). The importer and extractor now feed the milestone 3 Speakers workspace.

Milestone 2 is implemented and verified: 96 focused import/extraction tests passed. Of 89 eligible blank cells, the supplied corpus produced 29 proposals (26 title, zero caption-only, three transcript); 60 remained unresolved. The four existing cells and 161 excluded rows were preserved. Twenty talks were reviewed during development, with known missed guest attributions documented. These counts are not an accuracy estimate. See [validation/speaker-extraction.md](validation/speaker-extraction.md).

Milestone 3 is implemented and verified: the Speakers workspace supports upload/options, a local transcript path, editable numbered-talk review, evidence on demand, explicit approval, reset, and completed-CSV download. Manual edits survive reruns and extraction; only approved in-scope speaker cells can change. All 132 focused tests passed. A complete supplied-file UI run preserved 254 rows/21 columns, four existing values, and 161 excluded rows; source files remained unchanged. See [validation/speaker-review.md](validation/speaker-review.md).

| Milestone | Proposed change | Check before moving on |
| --- | --- | --- |
| **1. Import and eligibility — complete** | `finder/speaker_import.py`: CSV decoding, headers, text values, row identity, valid numbered scope, and lazy transcript matching | 93 eligible talks; original 254 rows/21 columns retained; prefilled cells preserved. |
| **2. Ordered extraction — complete** | `finder/speaker_extract.py`: separate title, caption, and transcript extractors with a shared main-speaker success contract | Title → caption → transcript order; no downstream extractor called after success. |
| **3. Review and export — complete** | Compact Speakers workspace in `app.py`, evidence on demand, editable values, completed-CSV download | Only accepted in-scope speaker cells change. |
| 4. Search handoff | Reviewed main-speaker record to existing search form/session state | Prefilling does not automatically trigger a network search. |
| 5. Optional model evaluation | Separate model adapter only if adopted after baseline evaluation | Main-speaker accuracy improves while preserving evidence validation and early stopping. |

Store the table, proposals, edits, and lazily built transcript index in session state. Cache DOCX opening text by file identity/content and invalidate when a file changes. Sorting the preview must not rerun extraction. Skipped sources must not trigger unnecessary document reads or model calls.

The folder path is local to the machine running Streamlit. Extract `TRANSCRIPTS V2.zip` before using it. ZIP upload and remote-machine folder access remain outside the first version.

## 7. Acceptance and evaluation

Review a representative sample of about 20 talks before claiming extraction quality, covering all three winning sources, placeholders, damaged names, institutions, introducers, moderators, ambiguous panels, and missing names. Review all numbered talks in the imported file for production acceptance (93 in the supplied sample).

Measure correctly accepted main speakers, incorrect fills, unresolved rows, and source usage separately. No accuracy percentage is available yet. Completing more cells is not a substitute for identifying the correct main speaker.

Required checks:

- Title success: caption extractor and transcript indexing/reading are not called.
- Title failure plus caption success: transcript is not read.
- `No description` or a missing caption: proceed to transcript only after title failure.
- Both earlier sources fail: exact reference matching reaches the correct DOCX.
- All three sources fail or remain ambiguous: the blank speaker cell stays blank.
- Caption fallback does not assume an announcer/moderator is the main speaker. Transcript fallback may retain such name mentions, all with `*`, while filtering recognized institutions and non-person terms.
- A multi-person `Speakers:` list is not arbitrarily reduced to its first person.
- No `YouTube title`, external search, or cross-document identity completion is introduced as an extra source.
- All 161 out-of-scope rows, four existing speaker cells, and original columns are preserved by default.
- Numeric references handle `5`/`05`, avoid `1`/`10` collisions, and expose duplicate/missing matches without silently selecting a file.
- Unicode names and CSV quoting/multiline fields round-trip correctly.
- Rule-only extraction makes no network requests and never writes source files.
- A reviewed main speaker reaches the search form without importing unrelated affiliations or changing existing social search behavior.

## 8. Remaining discussion

Scope, role, source order, and stopping behavior are settled and should not be reopened as defaults. The remaining design choice is whether to add optional LLM assistance immediately or evaluate the deterministic baseline first; the recommendation remains baseline first.

Explicit title participants can now fill multiple names. Caption panels without an identifiable main speaker remain unresolved. Transcript fallback collects recognized name mentions regardless of role, with `*` and source evidence; unrecognized names can still be missed.

Milestones 1–3 are complete. The next milestone is an explicit handoff of a reviewed main-speaker name to the social search form. Prefilling must retain platform choices and must not trigger a search automatically.
