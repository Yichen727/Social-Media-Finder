# Speaker review and export — milestone 3 verification

Recorded on 3 November 2026. The Speakers workspace is available from the workspace selector at the top of `app.py`. This milestone connects CSV import, ordered extraction, editable review, evidence, and completed-CSV download. Social-search handoff remains milestone 4.

## User flow

1. Choose **Speakers**, upload a CSV, and optionally enter the extracted transcript folder path on the machine running the app.
2. Check the import preview. **CSV options** provides encoding, delimiter, and target speaker-column selection when needed.
3. Click **Find speakers**. The existing title → YouTube Caption → DOCX cascade supplies suggestions for eligible blank cells.
4. Edit or clear names in the three-column review table. Open **Source evidence** and select a talk for the winning quotation, filename/paragraph/timestamp, or fallback reasons.
5. Click **Apply reviewed changes** to approve the current table, then **Download completed CSV**.

The preview contains eligible numbered talks only, with `Ref Number`, `High-res video name`, and editable `Speakers`. Stable original row IDs are hidden from display. No confidence columns or repeated per-row warning banners were added. Only the selected speaker field is editable; no rows can be inserted or deleted in the preview.

Existing speaker values appear unchanged unless explicitly edited. A blank transcript path allows title/caption-only extraction. An inaccessible nonblank path is reported without discarding edits. The app does not accept ZIP upload; extract the archive first.

## Review and session behavior

`finder/speaker_review.py` holds original imported data, suggestions, manual overrides, and the approved snapshot separately. `finder/speaker_workspace.py` renders the workspace and keeps its state in the Streamlit session.

- A suggestion is not approved merely because it appears in the editor. Download is disabled until **Apply reviewed changes** approves the current values across the numbered-talk table.
- Any subsequent change requires approval again before download. Returning exactly to the previously approved values restores that approval.
- **Find speakers** preserves manual overrides, including deliberate empty strings. The latest editor changes are consumed before extraction is rerun.
- **Reset review** explicitly discards manual edits and approval, retaining the latest machine suggestions and original existing values.
- Reprocessing the same data/options does not reimport the CSV or replace the review. Changing the file content or CSV interpretation options starts a separate review; this behavior is stated beside those options.
- Selecting evidence, editing, approving, or switching workspaces does not rerun extraction. DOCX parsing is cached by the existing extractor. A user-requested new extraction refreshes the lazy filename index and reuses unchanged DOCX openings.
- Workspace switching retains speaker edits and loaded input bytes even though Streamlit removes hidden widget state. Social platform choices, submitted form values, and previous results are preserved; switching never starts a search.
- These are in-session values, not persistent saved projects. Original CSV/DOCX files are never overwritten.

The editor's input snapshot stays fixed while editing, and suggestions/reset use a new widget generation. This avoids losing alternating edits through data-editor feedback. Review updates and exports use original row identity rather than the displayed order or reference number.

## Export guarantees

`SpeakerReview.export_csv()` rejects unapproved or changed drafts. It creates UTF-8 with BOM bytes, preserving source delimiter, header spelling/order, all rows, and all cells outside the selected speaker column. Even within that column, excluded rows remain unchanged. Existing nonblank values change only through explicit review edits.

The download is named `<original-name>_speakers_filled.csv`. Downloading writes a new file through the browser; application code does not overwrite the source. Original business columns such as `Match status` remain part of the source CSV export regardless of social-results display preferences.

## Verification

132 focused tests passed across import, extraction, review/export, workspace integration, and existing social dashboard tests:

```text
.venv\Scripts\python.exe -B -m pytest tests/test_speaker_import.py tests/test_speaker_extract.py tests/test_speaker_review.py tests/test_speaker_workspace.py tests/test_app.py -q -p no:cacheprovider
132 passed
```

New checks exercise approval gating, invalidating approval after editing, preserved manual clears across extraction, multiple consecutive edits, explicit reset, reordered review records, rejected out-of-scope edits, Unicode/CSV quoting/multiline values, alternate delimiters and singular headers, recoverable encoding/header errors, evidence access, workspace switching, and existing social search behavior. Network searches are mocked or forbidden during UI tests.

A separate Streamlit AppTest run used the supplied complete CSV and temporary copies of all 93 matching DOCX files:

| Check | Result |
| --- | ---: |
| Imported/exported data rows | 254 |
| Original columns preserved | 21 |
| Numbered rows in editable preview | 93 |
| Initial proposals from the unchanged rule baseline | 29 |
| DOCX openings read during Find speakers | 63 |
| Existing speaker cells preserved | 4 |
| Excluded rows preserved | 161 |
| Social-search calls | 0 |
| Repeated extraction / DOCX reads during edits and approval | 0 |

The verification cleared Ref 5's suggestion and entered **Herbie Hancock** manually for Ref 90, then approved and generated download bytes. These are test review choices, not silent changes to the extractor or the supplied CSV. The downloaded data contained exactly the approved values, preserved all non-speaker cells, retained leading zeroes/multiline fields, and began with a UTF-8 BOM. Byte/hash comparisons confirmed that the source CSV and verification DOCX copies were unchanged. No completed CSV was written to the user's source folder.

Machine-readable verification details are in [speaker-review.json](speaker-review.json). The extraction baseline's 60 unresolved rows and documented guest-attribution gaps remain unchanged; this milestone provides manual review rather than claiming improved extraction accuracy. Verification used Streamlit's server-side AppTest, not a visual browser audit.

## Next milestone

Add the explicit handoff of an accepted main-speaker name to the social search form. The current workspace neither prefills that form nor automatically searches imported names.
