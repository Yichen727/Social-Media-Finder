# Verification report

Recorded on **2 November 2026**, using Windows and Python 3.12.10. UI, documentation, and messages are in English. CSV export was omitted at the user's request.

## Automated checks

- **102 tests passed** (`.venv\Scripts\python.exe -m pytest -q`, latest run: 1.95 seconds).
- No tests contact search engines. Search responses, errors, and public-reference pages are mocked.
- Coverage includes required names; optional context; all three profile parsers; X/Twitter deduplication; non-profile and spoofed URLs; similar names; fan/news/archive rejection; evidence sources; error classification; bounded retries; explicit DDGS empty results; platform independence; partial failures; no results; English UI startup; validation messages; profile buttons; technical details; and refresh.
- `.venv\Scripts\python.exe -m pip check`: **No broken requirements found**.
- Windows launcher executed successfully with `run.bat --prepare-only` from the actual project path containing spaces. A repeat preparation reused dependencies without running installation.
- `run.command` passed `bash -n` using Git Bash. This is syntax validation, not a native macOS launch test.

## Local application startup

Streamlit started on `127.0.0.1:8517` in headless validation mode.

- `GET /_stcore/health`: **200**, body `ok`.
- `GET /`: **200**, Streamlit HTML returned.
- AppTest exercised the form, results, links, empty states, failures, and refresh without UI exceptions.

The validation server was stopped after checking it. A full graphical-browser appearance check and automatic default-browser opening were not exercised. Native macOS Finder/Terminal behavior remains untested.

## Real-network search checks

The opt-in script queried real DDGS search providers for three names across three platforms, using the final query strategy and matching rules. It performed 27 logical queries, with a five-second provider timeout and one adapter attempt per query. The normal app allows two attempts and an eight-second provider timeout.

| Person | Platform | Final status | Candidates |
| --- | --- | --- | ---: |
| Emma Watson | LinkedIn | Possible Match | 5 |
| Emma Watson | Instagram | No Reliable Match | 0 |
| Emma Watson | X / Twitter | No Reliable Match | 0 |
| Elon Musk | LinkedIn | Possible Match | 5 |
| Elon Musk | Instagram | No Reliable Match | 0 |
| Elon Musk | X / Twitter | No Reliable Match | 0 |
| Christopher Nolan | LinkedIn | Possible Match | 5 |
| Christopher Nolan | Instagram | Possible Match | 4 |
| Christopher Nolan | X / Twitter | Possible Match | 1 |

All final queries returned results or DDGS's explicit `No results found.` signal. No final query returned a timeout/HTTP/access error. Earlier runs did encounter provider problems and inconsistent coverage; these motivated region and error-classification fixes. The final run's empty outcomes **do not establish that a person has no account**. Even well-known profiles were missed by the providers in this environment.

No candidate was promoted to **Likely Official**. The live run did not establish any account's ownership and did not exercise a successful strong-reference fetch. Strong-reference rules, robots handling, redirects, local attribution, source independence, and reference failures were verified with mocked pages instead.

The full local diagnostic data is in `validation/live-search.json`. It contains real search responses, exact queries, and evidence. It is excluded from the distribution archive and is never loaded by application code. Candidate accounts in that diagnostic are unverified, including namesakes and potentially misleading self-described official accounts.

## Findings and limits

- Free-search coverage varied materially between runs. Manual fallback links are available for every planned query.
- The first DDGS configuration used a global region identifier that one backend interpreted as a language code. Switching to the documented `us-en` region removed that DNS issue.
- DDGS's exact `No results found.` exception represents an empty result set. Wrapped provider failures remain errors; regression tests cover both cases.
- X uses a simple `site:x.com/` discovery query and a separate `twitter.com` query, avoiding an OR expression in the initial site restriction.
- News/archive/fan results are filtered, but name-only matching remains ambiguous. Same-name accounts and impersonators cannot be reliably identified using snippets alone.
- The public-reference allowlist is deliberately small. A legitimate account often remains Possible Match because independent references are absent or inaccessible.

## Acceptance review

| Requirement | Result |
| --- | --- |
| Streamlit starts | Verified with AppTest and HTTP |
| Required full name; three optional fields | Implemented and tested |
| Three independently handled platforms | Implemented and tested |
| Clickable profile URLs and confidence | Implemented and tested |
| Non-profile filtering and account deduplication | Implemented and tested |
| Failure separate from no reliable match | Implemented and tested |
| Search errors do not crash the whole search | Implemented and tested |
| No paid API, LLM, or social login | Implemented |
| CSV export | Omitted at user's request |
| Windows launcher | Preparation mode verified; browser opening not exercised |
| macOS launcher | Bash syntax verified; native launch not tested |
| Automated tests | 102 passed |
| English README and project structure | Included |

The project is runnable locally. Live search was exercised, but reliable account discovery across every platform and graphical end-to-end operation are not claimed.

## Frontend cleanup

Removed the explanatory sidebar, refresh instruction caption, three summary metrics, and candidate evidence expanders at the user's request. The header now has a single description. Search, refresh, profile links, match statuses, manual search, and error details remain available. Evidence-based matching is unchanged in the backend. The existing automated suite passes after the cleanup.
