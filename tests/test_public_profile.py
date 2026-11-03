from unittest.mock import Mock

import pytest

from finder.models import Person, Platform, QueryRun, SearchHit
from finder.profile_parser import extract_candidates
from finder.public_profile import parse_followers, populate_public_details
from finder.service import FinderService


@pytest.mark.parametrize("text,count,note", [
    ("1,234 followers", 1234, "Indexed count"),
    ("2K followers · 500+ connections", 2000, "Rounded"),
    ("55M Followers, 1,442 Following", 55000000, "Rounded"),
    ("1.25 million followers", 1250000, "Rounded"),
    ("1.2B followers", 1200000000, "Rounded"),
    ("Followers: 6,440", 6440, "Indexed count"),
    ("Followers: 1.2K+", 1200, "Lower bound"),
    ("500+ followers", 500, "Lower bound"),
    ("over 1M followers", 1000000, "Lower bound"),
    ("about 300 followers", 300, "Approximate"),
    ("0 followers", 0, "Indexed count"),
    ("2 000 followers", 2000, "Indexed count"),
    ("2\u202f000 followers", 2000, "Indexed count"),
    ("2.5万粉丝", 25000, "Rounded"),
])
def test_follower_counts_are_numeric_but_preserve_precision(text, count, note):
    result = parse_followers(text)
    assert result.count == count and result.note == note
    assert result.display


@pytest.mark.parametrize("text", [
    "500+ connections", "1,442 following", "200 likes", "25 posts",
    "Followers: unavailable", "", "1,2K followers",
])
def test_other_metrics_or_unsupported_numbers_are_not_followers(text):
    assert parse_followers(text) is None


def candidate(platform=Platform.X, snippet="", title="Alex Morgan", url="https://x.com/alexmorgan"):
    return extract_candidates([SearchHit(title, url, snippet)], platform)[0]


def test_social_details_only_extract_followers_even_when_bio_contains_career_or_nationality():
    item = candidate(snippet="Location: London, United Kingdom · 2K followers")
    populate_public_details(item, Person("Alex Morgan", "Producer", "Example Studios", "British"))
    assert item.nationality == ""
    assert item.job_title == item.company == ""
    assert item.follower_count == 2000
    item.hits.append(SearchHit("Alex Morgan", item.url, "Nationality: British · Senior Creative Producer at Example Studios"))
    populate_public_details(item, Person("Alex Morgan"))
    assert item.nationality == item.nationality_source == ""
    assert item.job_title == item.company == ""
    assert item.follower_count == 2000


def test_follower_count_has_source_and_original_text():
    item = candidate(snippet="2K followers")
    populate_public_details(item, Person("Alex Morgan"))
    assert item.follower_source == item.url
    assert item.follower_display == "2K"


def test_exact_indexed_count_is_preferred_to_rounded_count():
    item = candidate(snippet="2K followers")
    item.hits.append(SearchHit("Alex Morgan", item.url, "2,148 followers"))
    populate_public_details(item, Person("Alex Morgan"))
    assert item.follower_count == 2148
    assert item.follower_note == "Indexed count"


def test_unrelated_profile_and_activity_do_not_supply_metadata():
    item = candidate(snippet="Activity: Another person has 55M followers")
    item.hits.append(SearchHit("Alexa Morgan", item.url, "80M followers · Nationality: American"))
    populate_public_details(item, Person("Alex Morgan"))
    assert item.follower_count is None
    assert item.nationality == ""


def test_profile_scoped_metric_lookup_ignores_different_profile_results():
    def search(query):
        if query.stage == "Public profile metrics":
            return QueryRun(query, hits=[
                SearchHit("Alex Morgan", "https://x.com/otheralex", "100M followers"),
                SearchHit("Alex Morgan", "https://x.com/alexmorgan", "2K followers"),
            ])
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alexmorgan", "")])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 1
    assert result.candidates[0].follower_count == 2000
    assert len([run for run in result.runs if run.query.stage == "Public profile metrics"]) == 1


def test_metrics_failure_does_not_remove_profile_or_invent_zero():
    def search(query):
        if query.stage == "Public profile metrics":
            raise TimeoutError("timeout")
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alexmorgan", "")])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.candidates[0].follower_count is None
    assert result.partial


def test_available_follower_count_needs_no_metrics_query():
    engine = Mock(search=lambda query: QueryRun(query, hits=[SearchHit(
        "Alex Morgan", "https://x.com/alexmorgan", "1,234 followers"
    )]))
    result = FinderService(engine).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.candidates[0].follower_count == 1234
    assert len(result.runs) == 3


def test_metrics_bio_can_supply_linkedin_career_fields():
    def search(query):
        snippet = "Senior Creative Producer at Example Studios · 2K followers" if query.stage == "Public profile metrics" else ""
        return QueryRun(query, hits=[SearchHit(
            "Alex Morgan", "https://www.linkedin.com/in/alex/", snippet
        )])
    result = FinderService(Mock(search=search)).search_platform(
        Person("Alex Morgan", "Creative Producer"), Platform.LINKEDIN)
    assert result.candidates[0].follower_count == 2000
    assert result.candidates[0].job_title == "Senior Creative Producer"
    assert result.candidates[0].company == "Example Studios"


def test_fan_disclosure_in_metrics_lookup_is_not_promoted_by_large_count():
    def search(query):
        snippet = "Fan account · 55M followers" if query.stage == "Public profile metrics" else ""
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alexmorgan", snippet)])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 1
    assert result.candidates[0].confidence == "Low"
    assert any("Fan" in note for note in result.candidates[0].cautions)
