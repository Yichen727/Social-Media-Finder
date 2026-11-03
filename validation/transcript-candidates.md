# Transcript name candidates and review markers

Recorded on 3 November 2026. Transcript fallback now collects name-shaped mentions throughout the existing opening window instead of requiring one attributable main speaker. This is the user's confirmed scope relaxation after the title-rule update.

## Behavior

- Keep the exact title → YouTube Caption → Transcript cascade and stop after an earlier success. Title and caption rules remain unchanged.
- Continue reading at most the opening 180 seconds, 8,000 characters, and 40 text paragraphs/turns. This change does not scan the entire talk.
- Collect full-name candidates from narration, introductions, panels, acknowledgments, quotations, and previous-session references. Participation and main-speaker status no longer filter transcript mentions.
- Collect cue-backed partial names such as `Alexandra` or `Mohammed` without guessing surnames. Normalize accents and deduplicate exact normalized names in first-mention order. Partial and full forms are not silently merged into one identity.
- Exclude diarization labels and common institution, location, role, and topic patterns. This remains lexical rule matching, not a complete named-entity recognition model.
- Retain original source paragraphs, timestamps, and diarization labels separately for each candidate's first mention. Evidence is displayed on demand, grouped by paragraph.

`Detection.name` / `Detection.names` remain undecorated, and a transcript detection has `requires_review=True` plus individual `NameMention` records. `SpeakerProposal.proposed_value` adds an asterisk to every transcript name. The preview and CSV use this marked value:

```text
Alexandra Munroe*; Michael Armitage*; Phil Tenari*; Reem Fadda*
```

Title/caption suggestions do not receive asterisks. Existing uploaded speaker cells are untouched. A single legend explains the marker in the interface. Users may edit/remove names or remove `*` after checking; explicit approval alone does not remove markers. All manual changes, including clears, continue to survive another Find speakers run. Changes require approval before downloading.

The original one-main-speaker transcript restriction and CSV panel/moderator-context rejection were removed. Session state retained across a code reload is migrated to the updated review class while preserving edits and approval data. Earlier CSV context neither supplies extra transcript names nor blocks detected mentions.

## Verification

178 focused tests passed across import, title/caption extraction, revised transcript behavior, review/export, workspace integration, and social-search regressions:

```text
.venv\Scripts\python.exe -B -m pytest tests/test_transcript_mentions.py tests/test_speaker_extract.py tests/test_speaker_review.py tests/test_speaker_workspace.py tests/test_speaker_titles.py tests/test_speaker_import.py tests/test_app.py -q -p no:cacheprovider
178 passed
```

Checks cover multiple introductions, moderators and previous-session mentions, narration without role cues, partial-name evidence, Unicode/initials/apostrophes/possessives, deduplication, sentence boundaries, individual source locations, generic organization/topic exclusions, unchanged early stopping and opening limits, stars in the actual review model and exported CSV, manual removal of markers, retained manual edits, and the UI legend/evidence display.

The corrected UTF-8 CSV and temporary copies of the original DOCX files produced:

| Outcome | Count |
| --- | ---: |
| Source rows / columns preserved | 254 / 21 |
| Eligible numbered talks | 93 |
| Existing speaker values preserved | 4 |
| Title successes | 38 |
| Transcript rows with candidates | 48 |
| Transcript candidate entries, before human review | 206 |
| Unresolved numbered blank cells | 3 |
| Excluded rows preserved | 161 |
| DOCX openings read | 51 |

Source CSV bytes and hashes of all 93 verification DOCX files were unchanged. In-memory export checks retained all non-speaker cells, existing speaker values, original rows/columns, and UTF-8 text. All automatic transcript names had `*` in the exported speaker field; title/caption values did not. No source file was overwritten. Full outcomes and source locations are in [transcript-candidates.json](transcript-candidates.json).

## Limits requiring review

These are candidate counts, not correct-speaker counts, an accuracy estimate, or a guarantee that all people were found. Actual results still contain false positives, including the work title `Maiden Voyage` and the place `Memphis Tennessee`. Organization names and work titles that resemble human names can pass the lexical rules. Conversely, uncommon spellings, lowercase names, some uncued first names, and people outside the opening window can be missed.

The broader output intentionally includes people discussed or thanked rather than participating in the talk. Transcript spelling errors are preserved as evidence rather than repaired from general knowledge. The asterisk therefore means **name candidate requiring manual verification**, not a confirmed speaker with a cosmetic marker. The workspace keeps that distinction visible without per-row warning banners.

No new dependency, API key, remote model call, or external search was added. Stronger semantic person/entity classification would be a separate improvement beyond this local rule baseline.
