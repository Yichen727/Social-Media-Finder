# Title extraction feedback — revised rules

Recorded on 3 November 2026, using `NEW Culture Summit High Resolution Content with Views and Metrics(Mapped Content) (1).csv`.

## Confirmed scope update

Titles can now supply multiple explicitly named participants, including conversation partners and title-named hosts. Their names stay in title order and are serialized with `; ` in one `Speakers` cell. This replaces the original single-main-speaker restriction for title extraction. Caption and DOCX extraction keep their existing role checks. A successful title still stops the row before either fallback is analyzed.

Ref 42 was confirmed as **Kader Attia**. The later clarification for Ref 26 includes **both Ai Da and Tim Marlow**; there is no Ai-Da exclusion. The spelling used in the source title is retained (`Ai Da` or `Ai-Da`), with Unicode normalization for combining accents.

## Feedback cases

| Ref | Expected and verified Speakers |
| --- | --- |
| 13 | Maja Hoffmann; Hashim Sarkis |
| 25 | Rita Wilson |
| 26 | Ai Da; Tim Marlow |
| 30 | Eddie Opara; Huda AbiFares; Sumitra Upham |
| 36 | Refik Anadol; Ralph Nauta |
| 41 | Sumayya Vally; Tim Marlow |
| 42 | Kader Attia |
| 47 | Michael Uslan; David Uslan |
| 53 | David Henry Hwang; Rana Kazkaz |

All nine succeed from the title alone, with caption extraction and transcript access prohibited in the regression checks. `.mp4` never becomes part of a name. The same format rules also identify the named title participants in Refs 9, 71, and 79.

## Rules

- Recognize `Creative Conversation with`, `Creative Conversations_`, `Screening + Conversation_`, and `A in conversation with B` formats.
- Locate explicit conversation attribution after a topic prefix, as in Ref 36, without treating the topic's capitalized words or commas as people.
- Split attributed names on `&`, `and`, `with`, and `in conversation with`; retain order and remove exact normalized duplicates.
- Recognize the named owner of a `[Name]'s Liner Notes` title with either straight or curly apostrophe.
- Remove topic/translation suffixes. Ref 13's `Sarkis-Creative ...` is separated while internal name hyphens such as `Jean-Luc` and `Zhu-Nowell` are preserved.
- Preserve accents, initials, particles, long names, and explicitly attributed mononyms. Undotted middle initials are supported within title names.
- Require each attributed fragment to be a complete supported name. A damaged/unfinished fragment or organization makes the title unresolved rather than filling only a plausible prefix.

There are no rules keyed by talk reference or expected person name. Ambiguous organization/multiple-role cases outside the reviewed title formats can still fall through. These remain deterministic patterns rather than general semantic entity recognition.

`Detection.names` exposes the automatically generated semicolon-separated names as a tuple for later handoff. It does not parse or rewrite existing uploaded speaker cells.

## Corrected-file verification

| Check | Result |
| --- | ---: |
| CSV encoding | UTF-8 with optional BOM |
| Original rows / columns | 254 / 21 |
| Eligible numbered talks | 93 |
| Existing speaker cells preserved | 4 |
| Blank numbered rows analyzed | 89 |
| Title successes with previous rules on this corrected CSV | 27 |
| Title successes with revised rules on the same CSV | 38 |
| Caption-only successes | 0 |
| DOCX successes | 1 |
| Total new speaker-cell proposals | 39 |
| Unresolved blank speaker cells | 50 |
| DOCX openings read | 51 |

The comparison uses the same corrected CSV on both sides. The earlier milestone 2 report used a different, Windows-1252 file with damaged text; its 26 title wins are a historical result, not the comparison baseline here. All previous title successes on the corrected file were retained. Ref 5 now succeeds from its correctly encoded accented title without a transcript fallback.

All source text, including Arabic captions/titles, remains unchanged. Extraction normalizes a temporary analysis copy; completed-CSV export preserves the original title cells, headers/order, all non-speaker cells, four prefilled speaker cells, and 161 excluded rows. Source CSV bytes and hashes of all 93 verification DOCX files were unchanged after checking export bytes.

The real nine feedback rows were also passed through the Streamlit review workspace: Find speakers, multi-name preview, explicit approval, and completed-CSV generation succeeded with caption/DOCX/social-network calls blocked. This is server-side AppTest verification, not a visual browser audit.

162 focused tests passed across title feedback, existing extraction/import, review/export, workspace integration, and social dashboard regression checks:

```text
.venv\Scripts\python.exe -B -m pytest tests/test_speaker_titles.py tests/test_speaker_import.py tests/test_speaker_extract.py tests/test_speaker_review.py tests/test_speaker_workspace.py tests/test_app.py -q -p no:cacheprovider
162 passed
```

Full outcomes are in [speaker-titles.json](speaker-titles.json). Counts describe proposals, not an overall accuracy claim. No source files or completed CSVs were written to the Downloads folder. Manual review remains necessary for unresolved cases.
