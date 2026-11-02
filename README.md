# Social Media Finder

A local, English-language dashboard for researching a person's public **LinkedIn, Instagram, and X / Twitter** accounts. Enter a name, optionally add context, and review candidate profiles with clickable links, match status, and confidence.

The application uses free web search. It requires **no API key, paid service, LLM, or social-platform login**. CSV export is intentionally omitted.

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
2. Optionally enter **Profession / Occupation**, **Organization / Affiliation**, and **Nationality / Country**. Leave unknown details blank.
3. Select **Search**. A spinner and platform status show progress.
4. Review the LinkedIn, Instagram, and X / Twitter sections. Up to five candidates are shown per platform.
5. Review each candidate's name, handle, match status, and confidence. Select **Open profile** to visit it.
6. Expand **Search queries & manual search** to inspect every query or open it in your browser.
7. Select **Refresh Search** to rerun searches for the person currently shown. To change the person or context, edit the form and select **Search**.

Results persist during normal Streamlit reruns in your browser session. There is no persistent search cache or automatic background refresh. Closing the session or restarting the app clears its results. Stopping the app: press **Ctrl+C** in its terminal.

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

1. **Search adapter:** `finder/search_engine.py` calls DDGS with `backend="auto"`, eight results per query, and an eight-second provider timeout. It attempts a query at most twice with a short exponential backoff. It distinguishes timeout, rate-limit, HTTP, connection, TLS, access-restriction, and generic provider errors. Access restrictions and TLS errors are not retried. The exact DDGS `No results found.` signal is treated as an empty search; wrapped HTTP/timeout errors remain failures. DDGS can contact multiple backends internally, so its timeout is not an overall search deadline.
2. **Query builder:** each platform gets three queries: broad name search, one contextual search, and an external reference search. The organization is preferred as contextual information, then profession, then country. Other supplied fields still help ranking. X searches `x.com` broadly and `twitter.com` in its second query, optionally adding context; other platforms get an “official” discovery query when context is empty. All optional conditions are never forced into every query.
3. **Profile parser:** accepts personal LinkedIn `/in/` pages and single-handle Instagram/X pages. Rejects posts, reels, stories, searches, reserved routes, spoofed domains, and non-web URLs. Removes tracking parameters and combines X/Twitter aliases. Profile links originate in search results; handles are never guessed.
4. **Identity matching:** full-name tokens, exact normalized handles, and supplied context provide weak evidence. Similar but different names and fan/parody wording are rejected. Candidates are sorted using an internal rule score; that score is not shown as an authenticity percentage.
5. **Public references:** at most two eligible pages per platform are checked for direct profile links with local name attribution. The small source policy currently covers BBC, Reuters, AP, Olympics, UN, EU, and UK government domains. BBC's two domains count as one source. A reference must match the person's name in its indexed title and fetched page title/heading. Generic social footers do not count. Fetches honor `robots.txt`; redirects, restricted pages, non-HTML responses, and oversized pages are skipped. Social-platform pages are never fetched. Two independent source families are required for “Likely Official.”

The search provider is behind a small `SearchProvider` contract, so another provider can replace DDGS without rewriting the UI or matching rules.

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

To create a clean distribution, run `.venv\Scripts\python.exe scripts\package_project.py` on Windows, or `.venv/bin/python scripts/package_project.py` on macOS. This creates `dist/Social-Media-Finder.zip` and preserves executable permissions for `run.command`. It excludes the local environment, caches, and raw live-search report.

Run the optional real-network checks separately:

```powershell
.\.venv\Scripts\python.exe scripts\live_search.py
# Or check just one person:
.\.venv\Scripts\python.exe scripts\live_search.py "Emma Watson"
```

On macOS, use `.venv/bin/python` in place of the Windows interpreter path. The script checks Emma Watson, Elon Musk, and Christopher Nolan across all three platforms by default. It writes `validation/live-search.json`, containing actual queries, candidates, evidence, and errors. It uses five-second provider timeouts with no adapter retries so diagnostics remain bounded; normal app settings are more tolerant. The JSON report is a development artifact, not a CSV export feature or application fixture. Never copy its candidate links into application logic.

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
    public_evidence.py           Bounded public reference checks
    service.py                   Independent platform orchestration
  scripts/
    live_search.py               Opt-in network validation
    package_project.py           Create the distributable ZIP
  tests/
    test_query_builder.py
    test_profile_parser.py
    test_identity_matcher.py
    test_search_engine.py
    test_service.py
    test_public_evidence.py
    test_app.py
  validation/
    REPORT.md                    Validation summary
```

DDGS usage follows the [official DDGS documentation](https://github.com/deedy5/ddgs). UI testing uses [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
