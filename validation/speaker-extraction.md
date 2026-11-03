# Ordered main-speaker extraction — milestone 2 verification

Latest transcript behavior: opening name mentions are now collected regardless of role and marked with `*`. See [transcript-candidates.md](transcript-candidates.md). This document retains the original, stricter milestone 2 results.

Historical baseline: the title policy has since been expanded to include explicitly named multiple participants. Current rules and corrected-CSV results are in [speaker-titles.md](speaker-titles.md). The counts below describe the original milestone 2 run.

Recorded on 3 November 2026. The deterministic backend is implemented in `finder/speaker_extract.py`. No dependencies were added. The upload/review interface and completed-CSV download remain milestone 3; social-search handoff remains milestone 4.

## Supplied-file run

The original Windows-1252 CSV and temporary extracted copies of the 93 supplied DOCX files were processed locally. Only numbered, eligible, blank-speaker rows were analyzed.

| Outcome | Rows |
| --- | ---: |
| Source CSV rows retained | 254 |
| Eligible numbered talks | 93 |
| Existing speaker values preserved without extraction | 4 |
| Blank numbered rows analyzed | 89 |
| New main-speaker proposals | 29 |
| Won at High-res video name | 26 |
| Won at YouTube Caption | 0 |
| Won at DOCX opening | 3 |
| Unresolved, blank values retained | 60 |
| Out-of-scope rows retained without extraction | 161 |
| DOCX openings actually read | 63 |

The extraction loop took about 0.13 seconds in this local run, with a fresh extractor cache and an already-built filename index. This is a local backend observation, not a UI or social-search latency guarantee. DOCX parsing was skipped for all 26 title successes. No caption-only winner occurred in this corpus: useful caption attributions generally duplicate successful titles; caption-only success is covered by focused fixtures.

The source CSV bytes and SHA-256 hashes of all 93 extracted DOCX files were unchanged after the run. The immutable imported table also serialized identically before and after extraction. No completed CSV was written and no original speaker cell was edited. Proposals await the milestone 3 review/export layer.

Per-reference outcomes, attempted sources, reasons, and winning evidence are recorded in [speaker-extraction.json](speaker-extraction.json). Counts describe proposals, not an accuracy measurement.

## Backend behavior

`SpeakerExtractor.extract_all(table)` returns one immutable `SpeakerProposal` per original row, retaining `row_id`, reference, and original speaker value. Statuses are `found`, `unresolved`, `preserved`, or `excluded`. `proposed_value` contains a proposed name only for a successful detection; otherwise it returns the original cell.

The source extractors share `Detection` records with `found`, `not_found`, `ambiguous`, or `unavailable` status:

1. `extract_title()` accepts explicitly attributed names, such as keynote/artist-talk/conversation titles. Multiple attributed people, institution names, and damaged names fall through.
2. `extract_caption()` requires a main/featured/keynote attribution, supports multiline labels, and rejects participant lists without a unique main role. Literal `No description` is unavailable.
3. `extract_transcript()` reads the matching DOCX only after both preceding sources fail. Explicit featured-speaker evidence outranks an introducer's self-introduction. A lone self-introduction is insufficient when the opening or already-attempted CSV fields establish a panel/moderator context.

A successful source returns immediately. There is no `YouTube title`, cross-document alias lookup, external identity search, network request, or LLM fallback. All unsuccessful sources leave the blank cell blank. Earlier failed fields supply session-role context only when a transcript fallback is needed.

DOCX parsing joins Word text runs, retains paragraph index/timestamp/diarization label, normalizes Unicode to NFC, and bounds the opening to 180 seconds, 8,000 characters, and 40 text paragraphs/turns by default. It stops at the first exceeded limit and never extracts from a truncated final paragraph. Multiple timestamped turns inside one Word paragraph are handled separately. Cached openings are invalidated when file size, modification time, or reading limits change. Missing/duplicate matches and unreadable DOCX files produce unresolved proposals rather than aborting the batch.

Example for the later UI integration:

```python
from finder.speaker_import import TranscriptIndex, load_speaker_csv
from finder.speaker_extract import SpeakerExtractor

table = load_speaker_csv(uploaded_bytes)
extractor = SpeakerExtractor(TranscriptIndex(transcript_folder))
proposals = extractor.extract_all(table)
# Review proposals before applying speaker-cell changes or exporting a new CSV.
```

## Reviewed sample

The following 20 talks were inspected against supplied titles, captions, and opening excerpts. This is a development review sample, including cases used to refine the rules, not a held-out benchmark or a complete reference set. Reading lower-priority evidence during this separate review does not change the application's early-stop behavior.

| Ref | Backend result | Review finding |
| --- | --- | --- |
| 5 | András Szántó, DOCX | Explicitly introduced to give the talk; Alexandra Munroe is the introducer. |
| 6 | Blank | Panel of musicians; no unique main speaker established. |
| 7 | Blank | Priya Kanchandani introduces a multi-person discussion; thanks to a previous session are not target speakers. |
| 8 | HE Omar Saif Ghobash, title | Explicit keynote attribution; honorific retained. |
| 9 | Christopher Kulendran Thomas, DOCX | The curator introduces a discussion with the featured artist; curator self-introduction is not selected. |
| 10 | Wole Soyinka, title | Explicit named conversation; no lower-source analysis during extraction. |
| 12 | Farah Al Qassimi, title | Title spelling retained; transcript variant does not override an earlier success. |
| 13 | Blank | Two named conversation participants without a unique main role. |
| 18 | Manuel Rabaté, DOCX | Institution-only title rejected; self-introduction identifies the case-study presenter. |
| 20 | Blank | Becky Anderson is explicitly the panel moderator, despite speaking alone in the bounded opening. |
| 21 | HE Sheikh Nahyan bin Mubarak Al Nahyan, title | Full attributed name, particles and honorific preserved. |
| 27 | Blank | Moderator plus multiple panelists; no arbitrary first-name selection. |
| 32 | Blank | First names and affiliations do not justify completing identities. |
| 45 | HE Razan Al Mubarak, title | Stops at title; does not append Khalifa from the caption. |
| 48 | H.E. Sheikh Salem bin Khalid Al Qassimi, title | Initials, honorifics and particles retained. |
| 55 | Babyface, title | Explicit professional mononym; no alias substitution from the transcript. |
| 57 | Glenn D. Lowry, title | Middle initial preserved; topic suffix excluded. |
| 64 | Blank | Institution and curator not accepted as main speaker. The excerpt names Ismael Mutaha as the invited representative; current rules miss that guest attribution, and the transcribed name needs review. |
| 65 | Erica Muhl, title | Earlier clear title wins despite damaged caption characters. |
| 90 | Blank | Known missed guest: the host explicitly introduces Herbie Hancock using “honored to be joined … for this session by”. This wording is outside the current featured-speaker rules. |

No unsupported accepted name was identified in this reviewed subset. Two useful guest-attribution cases remain unresolved. This does not establish precision or coverage for all 93 talks. All numbered talks still need production review.

## Automated checks

96 focused tests passed: 36 importer tests and 60 extractor tests.

```text
.venv\Scripts\python.exe -B -m pytest tests/test_speaker_import.py tests/test_speaker_extract.py -q -p no:cacheprovider
96 passed
```

Coverage includes early-stop spies (no caption call after title success; no transcript scan/read after caption success), exact reference fallback, placeholders, preservation of existing/excluded values, no `YouTube title` fallback, literal treatment of caption instructions, Unicode/initials/particles/mononyms, damaged names, organizations, multiple people, introducer-versus-featured roles, moderators, first-name-only evidence, DOCX run joining and metadata, all opening bounds, cache invalidation, malformed documents, and missing/duplicate transcript matches.

## Limits and next step

This is a conservative rule baseline, not general named-entity recognition or complete semantic role analysis. Names in unrecognized prose, some guest introductions, names split across DOCX paragraphs, and participants introduced after the opening window can be missed. Transcript transcription errors are retained as evidence rather than repaired from outside knowledge. Original CSV speaker values remain untouched even when they contain more than a person's name.

The next milestone is the compact review/edit/export workspace. It should keep unresolved values blank, expose supporting evidence on demand, preserve manual edits, and apply only reviewed speaker-cell changes. An optional model-assisted pass remains a separate decision after baseline review.
