from unittest.mock import Mock

import pytest

from finder.models import Person, Platform, SearchHit
from finder.profile_parser import extract_candidates
from finder.public_evidence import PublicEvidenceVerifier, safe_reference_url


@pytest.mark.parametrize("url", ["http://bbc.com/person", "https://bbc.com.evil.test/person",
                                "https://127.0.0.1/person", "https://x.com/alexmorgan",
                                "https://user@un.org/person", "https://un.org:8080/person"])
def test_untrusted_or_unsafe_urls_are_not_fetched(url):
    assert not safe_reference_url(url)


def fixture_data():
    candidate = extract_candidates([SearchHit("Alex Morgan", "https://x.com/alexmorgan", "")], Platform.X)[0]
    hit = SearchHit("Alex Morgan – profile", "https://www.un.org/people/alex", "")
    return candidate, hit


def test_direct_locally_attributed_link_is_strong_evidence():
    candidate, hit = fixture_data()
    verifier = PublicEvidenceVerifier(session=Mock())
    verifier._allowed = Mock(return_value=True)
    verifier._read = Mock(return_value=(200, '<title>Alex Morgan</title><p>Follow Alex Morgan <a href="https://twitter.com/AlexMorgan">on X</a></p>'))
    verifier.verify(Person("Alex Morgan"), [candidate], [hit])
    assert len(candidate.evidence) == 1 and candidate.evidence[0].strength == "strong"
    assert candidate.evidence[0].source_url == hit.url


@pytest.mark.parametrize("html", [
    '<title>Alex Morgan</title><footer><a href="https://x.com/alexmorgan">Our X account</a></footer>',
    '<title>Alex Morgan</title><p>Alex Morgan fan account <a href="https://x.com/alexmorgan">X</a></p>',
    '<title>Other Person</title><p>Alex Morgan <a href="https://x.com/alexmorgan">X</a></p>',
])
def test_footers_fans_and_wrong_person_pages_are_not_strong(html):
    candidate, hit = fixture_data()
    verifier = PublicEvidenceVerifier(session=Mock())
    verifier._allowed = Mock(return_value=True)
    verifier._read = Mock(return_value=(200, html))
    verifier.verify(Person("Alex Morgan"), [candidate], [hit])
    assert candidate.evidence == []


def test_robots_disallow_prevents_page_request():
    candidate, hit = fixture_data()
    verifier = PublicEvidenceVerifier(session=Mock())
    verifier._read = Mock(return_value=(200, "User-agent: *\nDisallow: /"))
    notes = verifier.verify(Person("Alex Morgan"), [candidate], [hit])
    assert len(notes) == 1 and candidate.evidence == []
    verifier._read.assert_called_once_with("https://www.un.org/robots.txt", robots=True)


def test_redirect_is_not_followed():
    session = Mock()
    response = Mock(status_code=302)
    session.get.return_value.__enter__ = Mock(return_value=response)
    session.get.return_value.__exit__ = Mock(return_value=False)
    verifier = PublicEvidenceVerifier(session=session)
    assert verifier._read("https://un.org/people/alex") == (302, "")
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_page_budget_is_bounded():
    candidate, hit = fixture_data()
    verifier = PublicEvidenceVerifier(session=Mock(), page_budget=100)
    verifier._allowed = Mock(return_value=False)
    hits = [SearchHit(hit.title, f"https://un.org/people/{index}", "") for index in range(10)]
    verifier.verify(Person("Alex Morgan"), [candidate], hits)
    assert verifier._allowed.call_count == 2
