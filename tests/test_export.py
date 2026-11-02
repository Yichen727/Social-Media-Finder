import csv
import io

from finder.export import COLUMNS, export_csv, result_rows, sort_rows
from finder.models import Candidate, MatchStatus, Person, Platform, PlatformResult, SearchHit


def example_results():
    return [
        PlatformResult(Platform.LINKEDIN, MatchStatus.POSSIBLE, candidates=[
            Candidate(Platform.LINKEDIN, "https://www.linkedin.com/in/alex/", "alex", "Alex Morgan",
                      job_title="Producer", company="Example Studios", nationality="British",
                      follower_count=2000, follower_display="2K", follower_note="Rounded",
                      hits=[SearchHit("Alex Morgan", "https://uk.linkedin.com/in/alex?trk=search", "")])
        ]),
        PlatformResult(Platform.INSTAGRAM, MatchStatus.POSSIBLE, candidates=[
            Candidate(Platform.INSTAGRAM, "https://www.instagram.com/alex/", "alex", "Alex Morgan",
                      follower_count=1200000, follower_display="1.2M", follower_note="Rounded")
        ]),
        PlatformResult(Platform.X, MatchStatus.FAILED),
    ]


def test_single_and_multiple_platform_filters():
    results = example_results()
    assert len(result_rows(Person("Alex Morgan"), results, [Platform.LINKEDIN])) == 1
    assert len(result_rows(Person("Alex Morgan"), results, [Platform.LINKEDIN, Platform.X])) == 2
    assert result_rows(Person("Alex Morgan"), results, []) == []


def test_required_columns_and_original_reference_link_are_retained():
    row = result_rows(Person("Alex Morgan"), example_results())[0]
    assert (row["Profession"], row["Company"], row["Nationality"], row["Followers"]) == (
        "Producer", "Example Studios", "British", 2000
    )
    assert row["Reference URL"] == "https://uk.linkedin.com/in/alex?trk=search"
    assert row["Profile URL"] == "https://www.linkedin.com/in/alex/"


def test_numeric_follower_ranking_and_unknowns_last_both_directions():
    rows = result_rows(Person("Alex Morgan"), example_results())
    descending = sort_rows(rows)
    assert [row["Followers"] for row in descending] == [1200000, 2000, None]
    assert [row["Rank"] for row in descending] == [1, 2, None]
    ascending = sort_rows(rows, "Followers (lowest first)")
    assert [row["Followers"] for row in ascending] == [2000, 1200000, None]
    assert rows[0]["Rank"] is None


def test_missing_metadata_not_filled_from_search_inputs():
    row = result_rows(Person("Alex Morgan", "Actor", "Other Company", "Canadian"), example_results())[1]
    assert row["Profession"] == row["Company"] == row["Nationality"] == ""
    assert row["Search Profession"] == "Actor" and row["Search Nationality / Country"] == "Canadian"


def test_failure_and_no_match_status_rows_are_preserved():
    results = [PlatformResult(Platform.X, MatchStatus.FAILED),
               PlatformResult(Platform.INSTAGRAM, MatchStatus.NONE)]
    rows = result_rows(Person("Alex Morgan"), results)
    assert {row["Match Status"] for row in rows} == {"Search Failed", "No Reliable Match"}
    assert all(row["Followers"] is None and not row["Profile URL"] for row in rows)


def test_csv_has_numeric_counts_bom_and_correct_quoting():
    rows = sort_rows(result_rows(Person("张伟"), example_results()))
    rows[0]["Company"] = 'Example, "Studio"\nLondon'
    encoded = export_csv(rows)
    assert encoded.startswith(b"\xef\xbb\xbf")
    restored = list(csv.DictReader(io.StringIO(encoded.decode("utf-8-sig"))))
    assert list(restored[0]) == list(COLUMNS)
    assert restored[0]["Followers"] == "1200000"
    assert restored[0]["Company"] == 'Example, "Studio"\nLondon'
    assert restored[0]["Search Name"] == "张伟"
    assert restored[-1]["Followers"] == ""


def test_spreadsheet_formulas_from_untrusted_text_are_escaped():
    rows = result_rows(Person("Alex Morgan"), example_results())
    rows[0]["Company"] = '=HYPERLINK("https://example.com")'
    restored = list(csv.DictReader(io.StringIO(export_csv(rows).decode("utf-8-sig"))))
    assert restored[0]["Company"].startswith("'=")


def test_no_platform_selection_exports_headers_only():
    assert len(export_csv([]).decode("utf-8-sig").splitlines()) == 1


def test_sort_by_company_retains_profile_ranks_and_unknowns_last():
    rows = result_rows(Person("Alex Morgan"), example_results())
    sorted_rows = sort_rows(rows, "Company (A–Z)")
    assert sorted_rows[0]["Company"] == "Example Studios"
    assert [row["Rank"] for row in sorted_rows] == [1, 2, None]
