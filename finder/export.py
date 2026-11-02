"""Shared list rows, stable ranking and Excel-friendly CSV output."""

import csv
import io
from collections.abc import Iterable

from finder.models import Person, Platform, PlatformResult

COLUMNS = (
    "Rank", "Platform", "Profile Name", "Username", "Profession", "Company", "Nationality",
    "Followers", "Follower Count Text", "Follower Count Note", "Match Status", "Confidence",
    "Reference URL", "Profile URL", "Follower Source URL", "Nationality Source URL",
    "Profession Source URL", "Company Source URL", "Search Time UTC",
    "Search Incomplete", "Search Error Count",
    "Search Name", "Search Profession", "Search Company", "Search Nationality / Country",
)
SORT_OPTIONS = (
    "Followers (highest first)", "Followers (lowest first)", "Name (A–Z)",
    "Company (A–Z)", "Profession (A–Z)", "Nationality (A–Z)",
)
VISIBLE_COLUMNS = (
    "Rank", "Platform", "Profile Name", "Profession", "Company", "Nationality",
    "Followers", "Follower Count Text", "Match Status", "Confidence", "Reference URL",
)


def _professional_source(candidate, label: str) -> str:
    return next((evidence.source_url for evidence in candidate.professional_evidence
                 if evidence.description.startswith(label)), "")


def result_rows(person: Person, results: Iterable[PlatformResult],
                platforms: Iterable[Platform] | None = None) -> list[dict]:
    allowed = set(platforms) if platforms is not None else set(Platform)
    rows = []
    for result in results:
        if result.platform not in allowed:
            continue
        base = {column: "" for column in COLUMNS}
        base.update({
            "Rank": None, "Platform": result.platform.value, "Followers": None,
            "Match Status": result.status.value, "Search Time UTC": result.searched_at,
            "Search Incomplete": result.partial, "Search Error Count": len(result.errors),
            "Search Name": person.full_name, "Search Profession": person.profession,
            "Search Company": person.organization, "Search Nationality / Country": person.country,
        })
        for candidate in result.candidates:
            reference = next((hit.url for hit in candidate.hits), candidate.url)
            rows.append({**base, "Profile Name": candidate.profile_name, "Username": candidate.handle,
                         "Profession": candidate.job_title, "Company": candidate.company,
                         "Nationality": candidate.nationality, "Followers": candidate.follower_count,
                         "Follower Count Text": candidate.follower_display,
                         "Follower Count Note": candidate.follower_note,
                         "Match Status": candidate.status.value, "Confidence": candidate.confidence,
                         "Reference URL": reference, "Profile URL": candidate.url,
                         "Follower Source URL": candidate.follower_source,
                         "Nationality Source URL": candidate.nationality_source,
                         "Profession Source URL": _professional_source(candidate, "Job title"),
                         "Company Source URL": _professional_source(candidate, "Company")})
        if not result.candidates:
            # Include status rows so an empty or failed platform is not silently omitted.
            rows.append(base)
    return rows


def sort_rows(rows: list[dict], sort_by: str = SORT_OPTIONS[0]) -> list[dict]:
    if sort_by not in SORT_OPTIONS:
        raise ValueError("Unsupported sort order.")
    if sort_by.startswith("Followers"):
        reverse_count = sort_by == "Followers (highest first)"
        def key(row):
            value = row["Followers"]
            return (not bool(row["Profile URL"]), value is None,
                    (-value if reverse_count else value) if value is not None else 0,
                    row["Profile Name"].casefold(), row["Platform"], row["Reference URL"])
    else:
        column = {"Name (A–Z)": "Profile Name", "Company (A–Z)": "Company",
                  "Profession (A–Z)": "Profession", "Nationality (A–Z)": "Nationality"}[sort_by]
        def key(row):
            return (not bool(row["Profile URL"]), not bool(row[column]), row[column].casefold(),
                    row["Profile Name"].casefold(), row["Platform"], row["Reference URL"])
    ordered = sorted(rows, key=key)
    rank = 0
    ranked = []
    for row in ordered:
        if row["Profile URL"]:
            rank += 1
        ranked.append({**row, "Rank": rank if row["Profile URL"] else None})
    return ranked


def _safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(rows: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({column: _safe_cell(row.get(column, "")) for column in COLUMNS} for row in rows)
    return output.getvalue().encode("utf-8-sig")
