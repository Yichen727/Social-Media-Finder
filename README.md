# Social Media Finder

A local, English-language dashboard for researching a person's public **LinkedIn, Instagram, and X / Twitter** accounts. Enter a name, select one or more platforms, and review a sortable list with profession, company, follower counts, and reference links. Download the filtered list as CSV.

The application uses free web search. It requires **no API key, paid service, LLM, or social-platform login**.

## 1. Requirements

- Windows 10/11 or a current macOS version.
- Python **3.11 or newer**, installed from [python.org](https://www.python.org/downloads/). On Windows, enable **Add python.exe to PATH** in the installer.
- An internet connection for the first installation and for searches.
- A folder you can write to. Extract the project before launching it; do not run it inside a ZIP file.

The launcher creates `.venv` inside the project and installs dependencies there. It does not change global Python packages or require an activated Conda environment. Packages listed in `requirements.txt` include the test runner. Streamlit also brings its own dependencies, including Pandas; this application does not directly use Pandas.

## 2. Launch on Windows

1. Extract the project into a normal folder, such as your Desktop.
2. Double-click **`run.bat`**.
3. On the first launch, wait for the private environment and package installation to finish.
4. The app opens in your default browser. Keep the terminal window open while using it.

Subsequent launches reuse installed packages after checking their versions. If an installation fails, the terminal remains open so you can read the error.

If Python is missing, the launcher shows the installation link. Install Python, close the terminal, then double-click `run.bat` again. The Windows Python launcher (`py`) is preferred; `python` is used as a fallback.

## 3. Launch on macOS

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/macos/). Run the installer's **Install Certificates.command** if offered.
2. Extract the project into a writable folder.
3. Double-click **`run.command`**.
4. Wait for installation, then use the browser window that opens. Keep Terminal open.

If macOS says the file cannot be executed, open Terminal, type `chmod +x ` (including the final space), drag `run.command` into Terminal, and press Return. Then double-click it again. For a downloaded-file warning, use Finder's **Open** action and approve it only after reviewing the source. You can also run the script from Terminal:

```bash
bash "/path with spaces/Social Media Finder Tool/run.command"
```

Both launchers support paths containing spaces. If you move the folder between computers or operating systems, delete or rename its old `.venv` first; virtual environments are not portable.

## 4. Find profiles

1. Enter **Full Name**. This is the only required field.
2. Select one or more **Platforms**. **Profession / Occupation** and **Company / Organization** appear only when LinkedIn is selected, and apply only to LinkedIn.
3. Select **Search**. Selected platforms run concurrently and completed results appear as they arrive.
4. Review the default **List** view. All matching-name profiles returned by the bounded searches are shown per searched platform, initially sorted by numeric follower count, highest first.
5. Use **Platforms in list** to include one or more searched platforms in the table and export. Choose **Sort by** for follower count or name, plus company/profession when LinkedIn is included. These controls do not repeat searches.
6. Select **Download CSV** to save the filtered list in the selected sort order. The UTF-8 CSV opens in Excel and other spreadsheet tools.
7. Open a clickable **Reference URL** to inspect the original source. Switch **View** to **Profiles** for individual profile buttons, search queries, manual search links, and technical details.
8. If follower counts remain missing, select **Fill missing Followers** to continue lookups without repeating discovery. Initial follower enrichment has a twelve-second scheduling budget per platform; in-flight provider requests may finish later. Account rows are kept even when their counts are deferred.
9. Select **Refresh Search** to rerun the same person and searched platforms. To change the person, context, or search scope, edit the form and select **Search**.

Live coverage checks and their limitations are recorded in [validation/REPORT.md](validation/REPORT.md).

The list includes namesakes and may include fan accounts. Compare the profile name, handle, and source link as well as follower count; a large count does not confirm identity.

Results persist during normal Streamlit reruns in your browser session. There is no persistent search cache or automatic background refresh. A session-only follower cache reuses successful counts for up to 24 hours when discovery omits them, avoiding repeated account lookups; CSV records the original observation time, source, and an earlier-observation note. Every refresh still attempts fresh queries. Closing the session or restarting the app clears its results. Stopping the app: press **Ctrl+C** in its terminal.

### Results list and CSV

The list contains **Rank, Platform, Profile Name, Followers, and Reference URL**, plus **Profession** and **Company** when LinkedIn is included. Instagram and X career fields stay blank in mixed-platform results. Social-only table views and CSV files omit career columns. CSV additionally includes username, canonical profile URL, field-source URLs, search time, query inputs, follower precision notes, and search completeness/error information.

- Followers are numeric for ranking: `2K` becomes `2000`, and `1.2M` becomes `1200000`. Rounded, approximate, and lower-bound counts are labeled in CSV.
- Counts reflect public search indexes, not guaranteed current measurements. Connections, following, likes, and posts are never substituted for followers. Unknown counts stay blank and sort after known values, including zero.
- X follower lookups query `x.com` only, using an exact-profile search followed by a handle-based search when needed. The legacy Twitter index is not queried. Indexed profile tabs (`with_replies`, `media`, `highlights`, and `reposts`) are merged into the same account. Instagram profile reels/tagged tabs are also supported. Individual posts and follower-list pages are excluded. Counts still depend on available public index text; missing data stays blank.
- Profession and company are extracted from LinkedIn only. Missing information stays blank; search inputs and another platform's uncertain identity are not copied into profile facts.
- Platforms with Search Failed or No Reliable Match retain status rows with blank profile fields.
- CSV follows the **Sort by** dropdown. Clicking a table header only changes the temporary table display order.
- CSV uses a UTF-8 BOM for Excel compatibility and escapes spreadsheet formula characters in untrusted text.

### Understanding statuses

| Status | Meaning |
| --- | --- |
| **Not Searched** | No completed search for this platform yet. |
| **Possible Match** | A candidate has supporting identity clues; ownership remains unconfirmed. |
| **Likely Official** | Two independent eligible public reference sources directly link the profile beside the person's name, and no fan/parody signal was found. This is still a research judgment. |
| **No Reliable Match** | All planned queries completed successfully, but no candidate passed the matching rules. This does not mean the person has no account. |
| **Search Failed** | At least one query failed and there is no usable candidate. The app cannot establish whether a reliable match exists. |

If some queries fail but others yield candidates, those candidates remain visible with an **incomplete results** warning. A failed request is never presented as a successful absence of matches. Public-reference fetch failures have their own technical notes and do not invalidate successful search requests.

**High, Medium, and Low confidence describe evidence quality, not a measured probability.** The app does not infer authenticity from follower counts, paid verification badges, the word “official,” or search position.

## 5. How it works

1. **Search adapter:** the UI's default service uses DDGS with an eight-second provider timeout, one adapter attempt per query, and up to twenty results. A completely failed social discovery gets one recovery query. The lower-level adapter still supports configurable retries. At most three provider calls run concurrently across selected platforms, discovery, and metric enrichment. Provider timeouts are not strict overall deadlines.
2. **Query builder:** LinkedIn keeps profession/company discovery and career lookups. Instagram and X each run two independent name/metric queries; X queries `x.com` only. Social platforms skip external-reference searches and verification. One additional search excluding leading handles can uncover more namesakes. Initial follower lookups run in rounds, giving accounts a primary lookup before a handle fallback, within a twelve-second scheduling budget. **Fill missing Followers** continues the remaining work without this initial budget. Valid session observations avoid repeated lookups.
3. **Profile parser:** accepts personal LinkedIn `/in/` pages and single-handle Instagram/X pages, plus the supported X profile tabs. Rejects posts, reels, stories, searches, reserved routes, spoofed domains, and non-web URLs. Removes tracking parameters and combines X/Twitter aliases. Profile links originate in search results; handles are never guessed.
4. **Identity matching:** full-name tokens and handles establish candidate identity clues. A profile-attributed LinkedIn job title and company receive more ranking weight than a matching username. Role matching distinguishes an exact profession from a compatible core role with missing seniority; “Creative Producer” never becomes “Senior Creative Producer” unless that text is returned by the index. Different names remain excluded. Matching-name fan/parody/news accounts remain available for comparison, with internal ownership cautions; follower count alone never establishes identity. Candidates are sorted using an internal rule score; that score is not shown as an authenticity percentage. Professional details improve identity ranking but do not establish official account ownership.
5. **Public references:** for LinkedIn only, at most two eligible pages are checked for direct profile links with local name attribution. The small source policy currently covers BBC, Reuters, AP, Olympics, UN, EU, and UK government domains. BBC's two domains count as one source. A reference must match the person's name in its indexed title and fetched page title/heading. Generic social footers do not count. Fetches honor `robots.txt`; redirects, restricted pages, non-HTML responses, and oversized pages are skipped. Social-platform pages are never fetched. Two independent source families are required for “Likely Official.”

The search provider is behind a small `SearchProvider` contract, so another provider can replace DDGS without rewriting the UI or matching rules.

### LinkedIn role and company extraction

`finder/linkedin_profile.py` parses LinkedIn result titles and the leading public profile introduction. For a headline such as “Senior Creative Producer at Example Studios / Agency Group”, it preserves the headline and extracts “Senior Creative Producer” as the job title and “Example Studios” as the company. A title formatted as “Name - Company | LinkedIn” can provide the company, while an explicit indexed Experience label can provide an affiliation. Each extracted field retains its source URL internally.

Activity posts, recruitment text, past-role wording, locations, truncated fields, and combined namesake results are excluded from role extraction. Indexed fields can still be incomplete or outdated; an Experience affiliation is not a guarantee of current employment. The application does not fetch LinkedIn HTML, access a logged-in session, or copy input values into missing metadata.

For the reported example, enter **Ross Ferguson** and **Senior Creative Producer**, leaving Organization blank. A real-network check on 2 November 2026 ranked `ross-ferguson-44750699` first and extracted **Senior Creative Producer** and **Atomized Studios** from the returned index text. Future search coverage can vary.

## 6. Limits and privacy

- Free search providers can throttle, block, time out, or return incomplete/outdated indexes. DDGS's own fallback behavior can take longer than one request timeout. Allow a few minutes on slow networks.
- A site's `site:` operator may be imperfectly honored by a provider. The URL parser still restricts displayed candidates to the requested platform.
- Public snippets cannot prove ownership. Common names can still yield the wrong person. Review the evidence before using an account.
- The narrow reference policy and exact-name rules favor caution. Nicknames, alternate transliterations, reordered names, sparse snippets, and missing references can lead to missed accounts. Many correct accounts will remain **Possible Match**. Lack of country or organization text is not treated as proof of a mismatch.
- Public-reference checks do not try to bypass login, CAPTCHA, bot restrictions, or robots rules. They do not discover arbitrary personal websites or scrape social profiles.
- The app binds to **127.0.0.1** and is intended for one person's local use. It has no user authentication or shared database.
- Search terms leave your computer and are sent to search providers. Eligible reference-page requests go to those publishers. Result state stays in memory; the application does not save a search history. Optional live-validation commands explicitly save a local report.
- Windows launch and Python behavior can be tested on this machine. Native Finder/Terminal behavior on macOS needs a separate macOS check.

## 7. Troubleshooting

| Symptom | What to do |
| --- | --- |
| Python not found | Install Python 3.11+ using the links above; enable PATH on Windows. |
| First installation fails | Check internet/proxy access to PyPI. Read the terminal error, resolve the connection issue, and launch again. |
| Search Failed / rate limit | Wait before refreshing. Open the manual search link. Other platforms can still succeed. |
| TLS or certificate error | Check your system clock and trusted certificates. Ask IT about the company proxy. Do not disable certificate verification. |
| CAPTCHA or access denied | Use the manual search link in your own browser. The app does not bypass restrictions. |
| No Reliable Match | Try a different spelling or add context. Inspect queries and use manual search. |
| Browser does not open | Copy the `http://127.0.0.1:...` URL printed in the terminal into your browser. |
| Port 8501 is in use | The launcher chooses another free local port and prints the URL. |
| `.venv` is broken or copied from another machine | Stop the app, rename `.venv` to `.venv-old`, and relaunch to recreate it. |
| `run.command` permission denied | Use the `chmod +x` steps above or run it with `bash`. |

## 8. Development and tests

The launchers handle package installation. Developers can prepare the environment without opening a browser:

```powershell
# Windows (Python must already be installed)
py -3 bootstrap.py --prepare-only
.\.venv\Scripts\python.exe -m pytest -q
```

```bash
# macOS
python3 bootstrap.py --prepare-only
.venv/bin/python -m pytest -q
```

Tests use mocks and Streamlit's AppTest; they do not contact search engines. They cover validation, query generation, canonical URLs, spoofed domains, posts, deduplication, incorrect names, fan accounts, direct-reference checks, retries, partial failures, empty results, and UI search/refresh behavior.

Additional tests cover LinkedIn headline/job/company parsing, profession-based ranking, missing seniority, namesake contamination, and lookup failures. List/export tests cover platform selection, refresh scope, numeric ranking, unknown counts, follower-versus-connection parsing, explicit nationality, original references, CSV quoting/formula escaping, table controls, and download availability.

To create a clean distribution, run `.venv\Scripts\python.exe scripts\package_project.py` on Windows, or `.venv/bin/python scripts/package_project.py` on macOS. This creates `dist/Social-Media-Finder.zip` and preserves executable permissions for `run.command`. It excludes the local environment, caches, and raw live-search report.

Run the optional real-network checks separately:

```powershell
.\.venv\Scripts\python.exe scripts\live_search.py
# Repeat Instagram/X coverage checks:
.\.venv\Scripts\python.exe scripts\live_search.py "Leo Messi" "Taylor Swift" "Alex Morgan" "Cristiano Ronaldo" --platforms instagram x --repeat 2
# Or check just one person:
.\.venv\Scripts\python.exe scripts\live_search.py "Emma Watson"
```

On macOS, use `.venv/bin/python` in place of the Windows interpreter path. The script checks Emma Watson, Elon Musk, and Christopher Nolan across all three platforms by default. It writes `validation/live-search.json`, containing actual queries, candidates, evidence, and errors. It uses five-second provider timeouts with no adapter retries so diagnostics remain bounded; normal app settings are more tolerant. The JSON report is a development artifact, not a CSV export feature or application fixture. Never copy its candidate links into application logic.

For the LinkedIn profession example, run `.venv\Scripts\python.exe -X utf8 scripts\check_linkedin.py` on Windows or `.venv/bin/python scripts/check_linkedin.py` on macOS. This checks Ross Ferguson with profession “Senior Creative Producer” and writes the actual response to `validation/linkedin-search.json`. That diagnostic file is excluded from the distribution archive and is never used as application data.

See [validation/REPORT.md](validation/REPORT.md) for the recorded verification results and limits.

## 9. Project files

```text
Social Media Finder Tool/
  app.py                         Streamlit dashboard
  bootstrap.py                   Private-environment setup and browser launch
  requirements.txt               Runtime and test dependencies
  run.bat                        Windows double-click launcher
  run.command                    macOS double-click launcher
  README.md
  .gitignore
  .streamlit/config.toml          Local binding, theme, and telemetry setting
  finder/
    __init__.py
    models.py                    Data contracts and input validation
    search_engine.py             Replaceable DDGS adapter and error handling
    query_builder.py             Staged queries and manual fallback links
    profile_parser.py            Strict profile URLs and deduplication
    identity_matcher.py          Evidence rules and candidate ranking
    linkedin_profile.py          Indexed LinkedIn role/company parsing and lookups
    public_profile.py            Indexed follower parsing and metric queries
    export.py                    List rows, ranking, and CSV serialization
    public_evidence.py           Bounded public reference checks
    service.py                   Independent platform orchestration
  scripts/
    live_search.py               Opt-in network validation
    package_project.py           Create the distributable ZIP
    check_linkedin.py             Opt-in profession-context validation
  tests/
    test_query_builder.py
    test_profile_parser.py
    test_identity_matcher.py
    test_linkedin_profile.py
    test_public_profile.py
    test_export.py
    test_search_engine.py
    test_service.py
    test_public_evidence.py
    test_app.py
  validation/
    REPORT.md                    Validation summary
```

DDGS usage follows the [official DDGS documentation](https://github.com/deedy5/ddgs). UI testing uses [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
