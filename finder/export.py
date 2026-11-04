"""Shared list rows, stable ranking and Excel-friendly CSV output."""

import csv
import io
from collections.abc import Iterable

from finder.models import Person, Platform, PlatformResult

COLUMNS = (
    "Rank", "Platform", "Profile Name", "Username", "Profession", "Company",
    "Followers", "Follower Count Note", "Follower Observed UTC",
    "Reference URL", "Profile URL", "Follower Source URL",
    "Profession Source URL", "Company Source URL", "Search Time UTC",
    "Search Incomplete", "Search Error Count",
    "Search Name", "Search Profession", "Search Company",
)
SORT_OPTIONS = (
    "Followers (highest first)", "Followers (lowest first)", "Name (A–Z)",
    "Company (A–Z)", "Profession (A–Z)",
)
VISIBLE_COLUMNS = (
    "Rank", "Platform", "Profile Name", "Profession", "Company",
    "Followers", "Reference URL",
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
        career = result.platform == Platform.LINKEDIN
        base = {column: "" for column in COLUMNS}
        base.update({
            "Rank": None, "Platform": result.platform.value, "Followers": None,
            "Search Time UTC": result.searched_at,
            "Search Incomplete": result.partial, "Search Error Count": len(result.errors),
            "Search Name": person.full_name, "Search Profession": person.profession if career else "",
            "Search Company": person.organization if career else "",
        })
        for candidate in result.candidates:
            reference = next((hit.url for hit in candidate.hits), candidate.url)
            rows.append({**base, "Profile Name": candidate.profile_name, "Username": candidate.handle,
                         "Profession": candidate.job_title if career else "",
                         "Company": candidate.company if career else "",
                         "Followers": candidate.follower_count,
                         "Follower Count Note": candidate.follower_note,
                         "Follower Observed UTC": candidate.follower_observed_at,
                         "Reference URL": reference, "Profile URL": candidate.url,
                         "Follower Source URL": candidate.follower_source,
                         "Profession Source URL": _professional_source(candidate, "Job title") if career else "",
                         "Company Source URL": _professional_source(candidate, "Company") if career else ""})
        if not result.candidates:
            # Keep an empty row for platforms without candidates.
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
                  "Profession (A–Z)": "Profession"}[sort_by]
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
    career_columns = {"Profession", "Company", "Profession Source URL", "Company Source URL",
                      "Search Profession", "Search Company"}
    has_linkedin = not rows or any(row["Platform"] == Platform.LINKEDIN.value for row in rows)
    columns = [column for column in COLUMNS if has_linkedin or column not in career_columns]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({column: _safe_cell(row.get(column, "")) for column in columns} for row in rows)
    return output.getvalue().encode("utf-8-sig")
