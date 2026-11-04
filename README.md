# Social Media Finder

Find public profiles on **LinkedIn, Instagram, and X**, compare follower counts, and export results to CSV. Use **Speakers Detection** to fill and review speaker names in CSV or XLSX files. No API key or social-platform login is required.

## Start

Install **Python 3.11 or newer** and extract the project into a folder.

- **Windows:** double-click `run.bat`.
- **macOS:** double-click `run.command`. If needed, run `bash run.command` from the project folder.

The first launch installs dependencies and opens the app in your browser. Keep the terminal open while using the app. Internet is required for first setup and social search. Speaker extraction runs locally.

## Search

1. Choose **Social search** and select one or more **Platforms**.
2. Enter a **Full Name**.
3. If LinkedIn is selected, optionally enter **Profession / Occupation** and **Company / Organization**. These details apply only to LinkedIn.
4. Click **Search**. Results appear as each platform finishes.

Instagram and X results contain names, follower counts, and profile links. LinkedIn results can also include profession and company.

## Review and export

- Use **Platforms in list** to filter results.
- Use **Sort by** to rank accounts by follower count or name. Company and profession sorting are available when LinkedIn is included.
- Open **Reference URL** to inspect the source, or switch to **Profiles** for profile links.
- Click **Download CSV** to export the filtered results in the selected sort order.
- Click **Refresh Search** to repeat the previous search. To change details or platforms, edit the form and click **Search**.

Follower counts may be rounded or outdated; recent counts may be reused during the current session. Blank values mean unavailable, not zero. Compare names and links as well as follower counts when identifying a person.

If a search fails, wait briefly and use **Refresh Search**, or try another spelling. To stop the app, press **Ctrl+C** in its terminal.

## Fill speakers

1. Open **Speakers Detection** (the default workspace) and upload your content **CSV or XLSX**. For XLSX, select a **Worksheet** if the workbook has several visible sheets. The first row must contain column headers, including **Ref Number**.
2. Optionally enter the **Transcript folder** path on the computer running the app. Extract your transcript ZIP first.
3. Click **Find speakers**. Rows with valid numeric **Ref Number** values are processed, using **High-res video name → YouTube Caption → DOCX opening**, stopping at the first successful source. Explicit title participants are kept in title order, separated by `; ` when there are several. Rows without recognizable names stay blank.
4. Edit or clear **Speakers** in the table. Check **Need Review** to show only blank or starred speaker cells; uncheck it to show all rows. Filtering keeps your edits and does not limit the download. Open **Source evidence** to check a suggestion. Transcript name candidates carry `*`, including hosts or people only mentioned. Check names and remove `*` after verification; the download retains any markers you leave in the table.
5. Click **Apply reviewed changes**, choose **CSV** or **XLSX** under **Export format**, then download the completed file. Both formats are available regardless of the input format. Later edits require approval again.

CSV settings are detected automatically. CSV-to-CSV export keeps the detected encoding, BOM, delimiter, and every source row and column. CSV-to-XLSX creates one worksheet and stores source values as literal text, preserving identifiers and leading zeroes.

XLSX-to-XLSX export retains the uploaded workbook and updates only approved, changed speaker cells in the selected worksheet, adding a Speakers column if needed. Other worksheet contents and workbook parts are copied from the original file; existing styles, formulas, and other cells are retained. Formula recalculation is requested when Excel opens the result. XLSX-to-CSV exports only the reviewed worksheet in UTF-8 with BOM, without workbook formatting or other sheets. Saved formula results are used when available; unrelated formula cells without cached results are exported as formula text.

Excel files are not recalculated during import. If a formula in a required source field has no saved result, open and save the workbook in Excel or LibreOffice first. Merged speaker cells must be unmerged before import. Legacy `.xls` and macro-enabled `.xlsm` files are not accepted.

Existing speaker values are preserved unless you edit them; source files are never overwritten. Repeating **Find speakers** keeps manual edits. **Reset review** discards manual edits and restores the latest suggestions. Changing the uploaded file or selected worksheet starts a new review. Changing only the export format keeps the review and approval. Review data stays in the current app session.

Sending reviewed names into social search will be added in the next step.
