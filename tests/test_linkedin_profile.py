from unittest.mock import Mock

import pytest

from finder.identity_matcher import rank_candidates
from finder.linkedin_profile import (
    build_detail_queries, extract_career_details, populate_career_details, title_match_level,
)
from finder.models import MatchStatus, Person, Platform, QueryRun, SearchHit
from finder.profile_parser import extract_candidates
from finder.service import FinderService


def profile(title, snippet="", handle="alex-morgan-123"):
    return SearchHit(title, f"https://www.linkedin.com/in/{handle}/", snippet)


def test_title_and_company_are_extracted_separately_with_source():
    hit = profile("Alex Morgan - Senior Creative Producer at Example Studios / Agency Group | LinkedIn")
    details = extract_career_details(hit, "Alex Morgan")
    assert details.job_title == "Senior Creative Producer"
    assert details.company == "Example Studios"
    assert details.headline == "Senior Creative Producer at Example Studios / Agency Group"
    candidate = extract_candidates([hit], Platform.LINKEDIN)[0]
    populate_career_details(candidate, Person("Alex Morgan"))
    assert candidate.job_title == details.job_title
    assert all(evidence.source_url == hit.url for evidence in candidate.professional_evidence)


def test_company_title_and_profession_in_introduction_are_combined():
    hit = profile("Alex Morgan - Example Studios | LinkedIn",
                  "Senior Creative Producer at Example Studios / Agency Group · Experience: Example Studios · Education: Example College")
    details = extract_career_details(hit, "Alex Morgan")
    assert (details.job_title, details.company) == ("Senior Creative Producer", "Example Studios")


def test_concatenated_namesake_snippet_cannot_override_the_company():
    details = extract_career_details(profile(
        "Alex Morgan - Other Company | LinkedIn",
        "Senior Creative Producer at Example Studios · Experience: Example Studios"
    ), "Alex Morgan")
    assert details.company == "Other Company"
    assert details.job_title == ""


def test_concatenated_provider_results_cannot_supply_another_persons_company():
    details = extract_career_details(profile(
        "Alex Morgan - Senior Private Sector Adviser ...Alex Morgan - Senior Finance Professional | LinkedIn",
        "View Alex Morgan’s profile on LinkedIn. Recognised finance leader · Experience: Other Company"
    ), "Alex Morgan")
    assert details.company == ""
    assert details.job_title == ""


def test_truncated_title_prefers_the_complete_leading_headline():
    details = extract_career_details(profile(
        "Alex Morgan - Senior Creative Producer at Example Studios ...Alex Morgan - Project Manager | LinkedIn",
        "Senior Creative Producer at Example Studios / Agency Group · Creative Producer. Works on film. · Experience: Unrelated Company"
    ), "Alex Morgan")
    assert details.headline == "Senior Creative Producer at Example Studios / Agency Group"
    assert details.job_title == "Senior Creative Producer"
    assert details.company == "Example Studios"


def test_short_about_text_does_not_invent_seniority():
    details = extract_career_details(profile("Alex Morgan - Example Studios | LinkedIn",
                                            "Creative Producer. Works with all digital mediums."), "Alex Morgan")
    assert details.job_title == "Creative Producer"
    assert title_match_level("Senior Creative Producer", details.job_title) == "compatible"
    assert "Senior" not in details.job_title


@pytest.mark.parametrize("snippet", [
    "Activity: Hiring a Senior Creative Producer at Other Studios.",
    "Alex Morgan reposted a Senior Creative Producer at Other Studios.",
    "Looking for a Senior Creative Producer at Other Studios.",
    "Formerly Senior Creative Producer at Other Studios.",
    "Experience: 2018–2020 Senior Creative Producer at Old Studios · Education: College",
    "Recommendations: Senior Creative Producer at Other Studios.",
])
def test_activity_hiring_and_historical_roles_are_not_current_role(snippet):
    details = extract_career_details(profile("Alex Morgan | LinkedIn", snippet), "Alex Morgan")
    assert details.job_title == ""
    assert details.company == ""


@pytest.mark.parametrize("title", [
    "Alexa Morgan - Senior Creative Producer at Other Studios | LinkedIn",
    "Alex Morgan - London, England, United Kingdom | LinkedIn",
    "Alex Morgan - Professional Profile | LinkedIn",
])
def test_wrong_names_and_locations_do_not_become_companies(title):
    details = extract_career_details(profile(title), "Alex Morgan")
    assert details.job_title == details.company == ""


@pytest.mark.parametrize("requested,indexed,level", [
    ("Senior Creative Producer", "Senior Creative Producer", "exact"),
    ("Senior Creative Producer", "Sr. Creative Producer", "exact"),
    ("Senior Creative Producer", "Creative Producer", "compatible"),
    ("Senior Creative Producer", "Junior Creative Producer", ""),
    ("Creative Producer", "Creative Director", ""),
    ("Producer", "", ""),
])
def test_profession_matching_distinguishes_role_and_seniority(requested, indexed, level):
    assert title_match_level(requested, indexed) == level


def test_ross_example_exact_profession_beats_same_name_handle():
    # Regression fixture supplied by the user; never loaded as application data.
    hits = [
        SearchHit("Ross Ferguson - Other Company | LinkedIn",
                  "https://www.linkedin.com/in/rossferguson/", "Digital Services Director"),
        SearchHit("Ross Ferguson - Atomized Studios | LinkedIn",
                  "https://www.linkedin.com/in/ross-ferguson-44750699/",
                  "Senior Creative Producer at Atomized Studios / Freuds · Experience: Atomized Studios"),
    ]
    matches = rank_candidates(extract_candidates(hits, Platform.LINKEDIN),
                              Person("Ross Ferguson", "Senior Creative Producer"))
    assert matches[0].handle == "ross-ferguson-44750699"
    assert matches[0].job_title == "Senior Creative Producer"
    assert matches[0].company == "Atomized Studios"
    assert matches[0].status == MatchStatus.POSSIBLE


def test_missing_seniority_still_ranks_the_role_above_unrelated_namesake():
    hits = [profile("Alex Morgan - Technology Director at Other Company | LinkedIn", handle="alexmorgan"),
            profile("Alex Morgan - Example Studios | LinkedIn", "Creative Producer. Works on film.", handle="alex-4475")]
    matches = rank_candidates(extract_candidates(hits, Platform.LINKEDIN),
                              Person("Alex Morgan", "Senior Creative Producer"))
    assert matches[0].handle == "alex-4475"
    assert matches[0].job_title == "Creative Producer"
    assert any("seniority" in caution for caution in matches[0].cautions)


def test_detail_lookup_is_scoped_and_bounded():
    candidates = extract_candidates([profile("Alex Morgan - Example Studios | LinkedIn", handle=f"alex-{i}")
                                     for i in range(10)], Platform.LINKEDIN)
    for candidate in candidates:
        populate_career_details(candidate, Person("Alex Morgan"))
    queries = build_detail_queries(Person("Alex Morgan", "Senior Creative Producer"), candidates)
    assert len(queries) == 2
    assert all("site:linkedin.com/in/alex-" in query.text for query in queries)


def test_scoped_details_enrich_and_rerank_without_copying_input_values():
    def search(query):
        if query.stage == "Broad search":
            return QueryRun(query, hits=[profile("Alex Morgan - Example Studios | LinkedIn")])
        if query.stage == "LinkedIn profile details":
            return QueryRun(query, hits=[profile("Alex Morgan - Example Studios | LinkedIn",
                                                "Creative Producer. Works with film.")])
        return QueryRun(query)
    result = FinderService(Mock(search=search)).search_platform(
        Person("Alex Morgan", "Senior Creative Producer"), Platform.LINKEDIN)
    assert result.candidates[0].job_title == "Creative Producer"
    assert result.candidates[0].company == "Example Studios"
    assert any(run.query.stage == "LinkedIn role fallback" for run in result.runs)
    assert any(run.query.stage == "LinkedIn profile details" for run in result.runs)
    assert len(result.runs) <= 7


def test_detail_lookup_failure_preserves_discovered_candidates():
    def search(query):
        if query.stage == "LinkedIn profile details":
            raise TimeoutError("timeout")
        return QueryRun(query, hits=[profile("Alex Morgan - Example Studios | LinkedIn")])
    result = FinderService(Mock(search=search)).search_platform(
        Person("Alex Morgan", "Creative Producer"), Platform.LINKEDIN)
    assert result.status == MatchStatus.POSSIBLE
    assert result.partial
    assert result.candidates[0].job_title == ""


def test_organization_and_profession_can_be_confirmed_together():
    matches = rank_candidates(extract_candidates([
        profile("Alex Morgan - Senior Creative Producer at Example Studios | LinkedIn"),
        profile("Alex Morgan - Chief Executive at Another Company | LinkedIn", handle="alexmorgan"),
    ], Platform.LINKEDIN), Person("Alex Morgan", "Senior Creative Producer", "Example Studios"))
    assert matches[0].handle == "alex-morgan-123"
    assert any(evidence.description.startswith("Company") for evidence in matches[0].evidence)
