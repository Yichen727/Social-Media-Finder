# Social Media Finder

Find public profiles on **LinkedIn, Instagram, and X**, compare follower counts, and export results to CSV. No API key or social-platform login is required.

## Start

Install **Python 3.11 or newer** and extract the project into a folder.

- **Windows:** double-click `run.bat`.
- **macOS:** double-click `run.command`. If needed, run `bash run.command` from the project folder.

The first launch installs dependencies and opens the app in your browser. Keep the terminal open while using the app. An internet connection is required.

## Search

1. Select one or more **Platforms**.
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
