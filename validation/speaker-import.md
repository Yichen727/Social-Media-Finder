# Speaker import — milestone 1 verification

Recorded on 3 November 2026. Implemented in `finder/speaker_import.py` without adding dependencies or changing the social search UI.

## Supplied-file results

| Check | Result |
| --- | ---: |
| CSV rows retained | 254 |
| Original columns retained | 21 |
| Eligible numbered talks | 93 |
| Existing speaker cells preserved | 4 |
| Numbered rows needing speakers | 89 |
| Unnumbered rows retained, excluded | 160 |
| Invalid reference rows retained, excluded | 1 (`YES`) |
| Exactly matched transcript files | 93 / 93 |
| Filename-index scans | 1 |
| DOCX bodies opened by the index | 0 |

The supplied CSV was decoded as Windows-1252. Serializing to UTF-8 with BOM and reading it back preserved every header and cell value, including multiline text and existing business columns. The source CSV and ZIP were checked byte-for-byte after verification and were unchanged.

The ZIP was copied into a temporary verification folder to exercise the real extracted filename layout. ZIP upload/extraction is not part of the application importer. The index only enumerated filenames and folder references; DOCX content reading was explicitly blocked during matching.

## Backend API

- `load_speaker_csv(data, ...)` imports uploaded bytes and exposes the selected encoding, delimiter, original headers, immutable source rows, eligible rows, and pending rows.
- Header lookup tolerates case and whitespace. Missing optional source columns remain unavailable. A missing speaker column is added; existing singular/plural speaker columns are reused. Having both requires an explicit choice.
- Invalid row widths, malformed quoting, ambiguous headers, and decoding failures raise a descriptive `SpeakerImportError` without dropping or shifting values.
- Duplicate references retain separate source row IDs and are excluded from automatic processing until resolved.
- `SpeakerCSV.to_csv_bytes()` returns a round-trip source CSV in memory; no source file is written.
- `TranscriptIndex(folder)` performs no folder scan at construction. `lookup(ref)` builds and caches a filename index on first use. It supports numbered DOCX filenames and numbered folders, and returns matched/missing/duplicate/conflicting/folder-error outcomes without guessing a file.
- `TranscriptIndex.refresh()` invalidates the index without immediately scanning again. Later extraction should call `lookup` only when both title and caption stages have failed.

## Tests and scope

**36 focused tests passed in 0.15 seconds.** They cover supported encodings/delimiters, quoted multiline fields, leading zeroes, header aliases, source immutability, duplicate/invalid references, scope, lazy indexing, exact reference matching, generic transcript filenames, metadata-file exclusion, conflicts, missing folders, and index invalidation.

No names were extracted or filled. No LLM/network requests were made. CSV upload widgets and review/download UI remain milestone 3; social-search handoff remains milestone 4.

Exact source hashes and the 93 reference-to-filename matches are in `validation/speaker-import.json`.
