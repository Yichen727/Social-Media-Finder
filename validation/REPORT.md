# Search performance update — 3 November 2026

**195 tests passed in 4.51 seconds.** The checks cover concurrent discovery/platform execution, bounded initial follower enrichment, manual continuation, cached metric reuse, X-only search scope, and LinkedIn-only career parsing/queries/table/CSV fields.

## Scheduling comparison

Recorded real celebrity search responses were replayed with an artificial 80 ms delay per provider call. The comparison used the same optimized query plan with sequential versus concurrent scheduling; it is not a wall-clock comparison against the previous application release.

Sequential scheduling: **0.878 s**. Concurrent scheduling: **0.572 s** (34.9% lower). Both made 18 queries and returned exactly the same 20 profile URLs and follower counts (14 known counts). Peak concurrent provider requests stayed within three.

## Live check

Alex Morgan was searched on Instagram and X twice with the normal default service and provider settings. The second round reused the same in-memory follower cache when observations were available. All X discovery and metric requests were scoped to x.com; the legacy Twitter index was never queried.

| Round | Platform | Ready after seconds | Profiles | Known followers | Query errors |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Instagram | 19.55 | 2 | 2 | 2 |
| 1 | X / Twitter | 32.10 | 10 | 4 | 4 |
| 2 | Instagram | 19.38 | 7 | 7 | 2 |
| 2 | X / Twitter | 31.84 | 9 | 4 | 4 |

This live session encountered provider timeouts. Failed or empty responses are not evidence of successful search-speed improvement. The replay demonstrates scheduling savings with usable results; normal-network end-to-end speed still depends on the provider. The twelve-second budget limits starting new follower lookups, not the total search duration or the duration of requests already in flight.

Exact replay and live records are in `validation/search-performance.json`. This diagnostic file is excluded from the distribution ZIP and is never loaded by the application.

## Earlier coverage checks

The results below were recorded before the performance optimization, with the earlier query plan, eight-second/two-attempt adapter, and unbounded full enrichment. They are historical observations, not a fresh coverage benchmark for the optimized default.

# Verification report — 3 November 2026

## Coverage and follower extraction

Four names were searched on Instagram and X, twice each, for 16 fresh platform searches. These checks exercised the actual DDGS adapter and application search service, without mocking search responses. The public-reference verifier was disabled to focus on discovery and follower attribution. Settings matched the normal adapter: eight-second provider timeout, two attempts, and up to twenty results per query. Two platform searches ran concurrently, with up to three metric lookups within each; the UI normally processes platforms sequentially. This extra diagnostic concurrency can increase provider load.

Each cell below is **returned matching-name accounts / accounts with a follower count**. Accounts may be namesakes, fan accounts, or self-described official accounts; this report does not establish ownership. Repeated counts are observations from two searches, not unique account totals.

| Name | Platform | Round 1 | Round 2 | Query errors, rounds 1 / 2 |
| --- | --- | ---: | ---: | ---: |
| Leo Messi | Instagram | 3 / 3 | 3 / 3 | 0 / 1 |
| Leo Messi | X / Twitter | 5 / 3 | 7 / 4 | 4 / 8 |
| Taylor Swift | Instagram | 3 / 3 | 3 / 3 | 1 / 1 |
| Taylor Swift | X / Twitter | 4 / 2 | 6 / 3 | 6 / 6 |
| Alex Morgan | Instagram | 10 / 10 | 9 / 9 | 0 / 2 |
| Alex Morgan | X / Twitter | 9 / 4 | 10 / 4 | 9 / 13 |
| Cristiano Ronaldo | Instagram | 1 / 1 | 1 / 1 | 1 / 2 |
| Cristiano Ronaldo | X / Twitter | 4 / 3 | 4 / 3 | 7 / 6 |

Across all searches, 59 of 82 returned account observations had follower counts. 8 of 16 searches had counts for every returned account.

27 accounts had known counts in both rounds; 27 returned the same numeric value in both rounds. Matching repeated values demonstrates repeatability of those index observations, not independent verification or freshness.

## What changed

- Removed the five-profile output limit and retained matching-name fan/news accounts for comparison. Unrelated names merely mentioning the target remain excluded.
- Increased each query's requested result limit from eight to twenty, added follower-focused discovery, and added one search excluding the first three discovered handles to uncover additional namesakes.
- Every returned account with a missing count receives a profile-specific lookup. Instagram has one fallback; X has two. Up to three such account lookups run concurrently. Access/rate-limit/TLS errors stop further lookups for that account.
- In the UI session, a failed fresh lookup can reuse the same account's last successful observation for up to 24 hours. CSV includes the original observation time, source, and an earlier-observation note. This cache is memory-only, never saved to disk. The 16 fresh diagnostic cases above did not reuse cached counts; cache recovery and expiry were separately checked in regression tests.
- Recognized Instagram reels/tagged profile tabs and X replies/media/highlights/reposts tabs, deduplicated to the same account. Individual posts and follower-list pages remain excluded.
- Accepted exact known handles in metric result titles, retained the metric source URL, and excluded counts explicitly attributed to another platform.
- The results table and CSV retain numeric Followers and share numeric sorting. Unknown counts stay blank and sort after known counts, including zero. Removed nationality/status/confidence/text-count columns remain excluded.

## Automated checks

**185 tests passed in 4.36 seconds.** No offline test contacts a search engine. Coverage includes more than five namesakes, metrics for every returned account, exact account attribution, alias-domain and handle-query fallbacks, profile-tab parsing, cross-platform count rejection, numeric sorting, CSV safety, UI controls, failure states, session fallback, and cache expiry.

## Limits

The live checks still encountered timeouts and incomplete public snippets. A blank count is unknown, not zero. The free public-search approach therefore does not guarantee complete or real-time follower coverage for every account. Higher follower count is useful for comparison but does not establish that an account belongs to the intended person.

Exact queries, returned snippets, metric source links, and errors are recorded in `validation/celebrity-coverage.json`. The application never loads this diagnostic file; the distribution ZIP excludes it.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\live_search.py "Leo Messi" "Taylor Swift" "Alex Morgan" "Cristiano Ronaldo" --platforms instagram x --repeat 2 --fresh --no-reference-check --output validation/coverage-recheck.json
.\.venv\Scripts\python.exe -m pytest -q
```
