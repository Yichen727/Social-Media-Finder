"""Coverage and follower attribution regressions from the live celebrity checks."""

from unittest.mock import Mock

import pytest

from finder.export import COLUMNS, VISIBLE_COLUMNS
from finder.identity_matcher import rank_candidates
from finder.models import Person, Platform, QueryRun, SearchHit
from finder.profile_parser import extract_candidates, normalize_profile_url
from finder.public_profile import parse_followers, populate_public_details
from finder.service import FinderService


@pytest.mark.parametrize("url,canonical", [
    ("https://www.instagram.com/alexmorgan13/reels/", "https://www.instagram.com/alexmorgan13/"),
    ("https://www.instagram.com/thealexmorgan/tagged/", "https://www.instagram.com/thealexmorgan/"),
    ("https://mobile.x.com/taylorswift13/with_replies", "https://x.com/taylorswift13"),
    ("https://x.com/taylorswift13/reposts", "https://x.com/taylorswift13"),
])
def test_account_tabs_keep_the_exact_account_identity(url, canonical):
    assert normalize_profile_url(url)[1] == canonical


def test_more_than_five_namesakes_survive_ranking():
    hits = [SearchHit("Alex Morgan", f"https://x.com/alex{i}", "") for i in range(12)]
    hits.append(SearchHit("Alexa Morgan", "https://x.com/alexa", "Friend of Alex Morgan"))
    matches = rank_candidates(extract_candidates(hits, Platform.X), Person("Alex Morgan"))
    assert len(matches) == 12
    assert "alexa" not in {item.handle for item in matches}


def test_every_namesake_can_receive_a_follower_lookup():
    def search(query):
        if query.stage == "Public profile metrics":
            handle = query.text.split("site:x.com/", 1)[1].split()[0]
            return QueryRun(query, hits=[SearchHit(f"@{handle} / X", f"https://x.com/{handle}", "2K Followers")])
        return QueryRun(query, hits=[SearchHit("Alex Morgan", f"https://x.com/alex{i}", "") for i in range(7)])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 7
    assert all(item.follower_count == 2000 for item in result.candidates)
    assert sum(run.query.stage == "Public profile metrics" for run in result.runs) == 7


def test_x_handle_lookup_recovers_counts_without_copying_other_profiles_or_posts():
    def search(query):
        if query.stage == "Public profile metrics":
            if 'site:x.com "alex"' in query.text:
                return QueryRun(query, hits=[
                    SearchHit("@alex / X", "https://x.com/alex/with_replies", "12.5K Followers"),
                    SearchHit("Alex Morgan", "https://x.com/other", "99M Followers"),
                ])
            return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex/status/1", "500M Followers")])
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "")])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.candidates[0].follower_count == 12500
    assert result.candidates[0].follower_source == "https://x.com/alex/with_replies"


def test_broader_x_handle_lookup_runs_after_exact_profile_lookup():
    def search(query):
        if query.stage == "Public profile metrics":
            hits = [SearchHit("@alex / X", "https://x.com/alex", "600 Followers")] if 'site:x.com "alex"' in query.text else []
            return QueryRun(query, hits=hits)
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "")])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.candidates[0].follower_count == 600
    assert sum(run.query.stage == "Public profile metrics" for run in result.runs) == 2


def test_x_does_not_receive_the_instagram_count_mentioned_in_a_bio():
    assert parse_followers("500M followers on Instagram", Platform.X) is None
    assert parse_followers("500M followers on Instagram · 12K followers", Platform.X).count == 12000


def test_live_x_header_sample_preserves_source_and_precision():
    url = "https://x.com/taylorswift13/reposts"
    item = extract_candidates([SearchHit("@taylorswift13 / X", url,
        "Joined December 2008 0 Following 83.9M Followers Mention Follow PostsPosts RepliesReplies")], Platform.X)[0]
    populate_public_details(item, Person("Taylor Swift"))
    assert item.follower_count == 83900000
    assert item.follower_note == "Rounded" and item.follower_source == url


def test_removed_columns_cannot_reappear_in_table_or_csv():
    removed = {"Nationality", "Match Status", "Confidence", "Follower Count Text", "Nationality Source URL", "Search Nationality / Country"}
    assert not removed.intersection(COLUMNS)
    assert not removed.intersection(VISIBLE_COLUMNS)


def test_failed_refresh_reuses_same_account_count_with_original_time_and_source():
    cache = {}
    def success(query):
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "2K Followers")])
    first = FinderService(Mock(search=success), follower_cache=cache).search_platform(Person("Alex Morgan"), Platform.X)
    observed = first.candidates[0].follower_observed_at
    def unavailable(query):
        if query.stage == "Public profile metrics":
            raise TimeoutError("temporary timeout")
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "")])
    second = FinderService(Mock(search=unavailable), follower_cache=cache).search_platform(Person("Alex Morgan"), Platform.X)
    assert second.candidates[0].follower_count == 2000
    assert second.candidates[0].follower_source == "https://x.com/alex"
    assert second.candidates[0].follower_observed_at == observed
    assert "Earlier observation" in second.candidates[0].follower_note
    assert not any(run.query.stage == "Public profile metrics" for run in second.runs)


def test_old_observations_expire_and_never_fill_a_different_account():
    from datetime import datetime, timedelta, timezone
    saved = {"follower_count": 1000, "follower_display": "1K", "follower_note": "Rounded",
             "follower_source": "https://x.com/alex",
             "follower_observed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    def search(query):
        if query.stage == "Public profile metrics":
            return QueryRun(query)
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", ""),
                                    SearchHit("Alex Morgan", "https://x.com/other", "")])
    result = FinderService(Mock(search=search), follower_cache={"https://x.com/alex": saved}).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 2
    assert all(candidate.follower_count is None for candidate in result.candidates)
