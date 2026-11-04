import pytest

from finder.models import Platform, SearchHit
from finder.profile_parser import extract_candidates, normalize_profile_url


@pytest.mark.parametrize("url,platform,canonical", [
    ("http://uk.linkedin.com/in/Alex-Morgan/?trk=foo", Platform.LINKEDIN, "https://www.linkedin.com/in/alex-morgan/"),
    ("https://www.instagram.com/Alex.Morgan/?igsh=abc#bio", Platform.INSTAGRAM, "https://www.instagram.com/alex.morgan/"),
    ("https://mobile.twitter.com/AlexMorgan?ref=foo", Platform.X, "https://x.com/alexmorgan"),
    ("https://www.x.com/alexmorgan/", Platform.X, "https://x.com/alexmorgan"),
    ("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fx.com%2FAlexMorgan", Platform.X, "https://x.com/alexmorgan"),
])
def test_profile_urls_are_canonicalized(url, platform, canonical):
    actual = normalize_profile_url(url)
    assert actual and actual[:2] == (platform, canonical)


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/company/example/", "https://linkedin.com/jobs/123/",
    "https://linkedin.com/posts/alex", "https://linkedin.com/learning/course/",
    "https://linkedin.com/search/results/", "https://linkedin.com/in/alex/recent-activity/",
    "https://instagram.com/p/abc/", "https://instagram.com/reel/abc/",
    "https://instagram.com/stories/alex/123/", "https://instagram.com/explore/",
    "https://instagram.com/explore/tags/name/", "https://instagram.com/accounts/",
    "https://instagram.com/direct/", "https://instagram.com/..alex/",
    "https://x.com/alex/status/123", "https://twitter.com/search?q=name",
    "https://x.com/hashtag/alex", "https://x.com/explore", "https://x.com/i/flow/login",
    "https://x.com/usernamewaytoolong", "https://x.com/home",
    "https://x.com.evil.test/alex", "https://evilinstagram.com/alex/",
    "https://linkedin.com.evil.test/in/alex/", "https://x.com@evil.test/alex",
    "https://someone@x.com/alex", "https://x.com:8080/alex", "javascript:alert(1)",
    "https://x.com/alex%2Fstatus%2F123", "https://x.com//alex", "not a url",
    "https://duckduckgo.com/l/?uddg=https://duckduckgo.com/l/", "https://[bad/alex",
])
def test_non_profiles_and_spoofed_domains_are_rejected(url):
    assert normalize_profile_url(url) is None


def test_x_aliases_deduplicate_but_keep_search_evidence():
    hits = [SearchHit("Alex Morgan", "https://twitter.com/AlexMorgan?utm_source=x", "First"),
            SearchHit("Alex Morgan | X", "https://x.com/alexmorgan", "Second")]
    candidates = extract_candidates(hits + hits, Platform.X)
    assert len(candidates) == 1
    assert len(candidates[0].hits) == 2
    assert candidates[0].url == "https://x.com/alexmorgan"


def test_platform_results_do_not_mix():
    assert extract_candidates([SearchHit("Name", "https://x.com/alex", "")], Platform.LINKEDIN) == []
