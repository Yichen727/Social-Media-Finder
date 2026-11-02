from unittest.mock import Mock

from finder.models import MatchStatus, Person, Platform, QueryRun, SearchError, SearchHit
from finder.service import FinderService


def test_initial_status_is_not_searched():
    from finder.models import PlatformResult
    assert PlatformResult(Platform.X).status == MatchStatus.NOT_SEARCHED


def test_successful_empty_search_is_no_reliable_match():
    engine = Mock(search=lambda query: QueryRun(query))
    result = FinderService(engine).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.status == MatchStatus.NONE
    assert len(result.runs) == 3


def test_failure_does_not_break_other_platforms():
    def search(query):
        if "site:linkedin.com/in/" in query.text:
            raise TimeoutError("timeout")
        return QueryRun(query)
    results = FinderService(Mock(search=search)).search_all(Person("Alex Morgan"))
    assert results[0].status == MatchStatus.FAILED
    assert all(result.status == MatchStatus.NONE for result in results[1:])


def test_partial_failure_with_no_candidate_is_failure():
    engine = Mock()
    engine.search.side_effect = lambda query: QueryRun(query, error=SearchError("timeout", "Timed out", "timeout")) if query.stage == "Broad search" else QueryRun(query)
    result = FinderService(engine).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.status == MatchStatus.FAILED and result.partial


def test_partial_failure_preserves_candidates_with_warning():
    def search(query):
        if query.stage == "Broad search":
            return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alexmorgan", "Alex Morgan, Scientist")])
        raise TimeoutError("timeout")
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.status == MatchStatus.POSSIBLE
    assert len(result.candidates) == 1 and result.partial


def test_verification_failure_does_not_discard_search_results():
    engine = Mock(search=lambda query: QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alexmorgan", "")]))
    verifier = Mock()
    verifier.verify.side_effect = RuntimeError("Verification unavailable")
    result = FinderService(engine, verifier).search_platform(Person("Alex Morgan"), Platform.X)
    assert result.status == MatchStatus.POSSIBLE
    assert "unavailable" in result.verification_notes[0]


def test_searches_are_never_cached():
    engine = Mock()
    engine.search.side_effect = lambda query: QueryRun(query)
    service = FinderService(engine)
    service.search_all(Person("Alex Morgan"))
    service.search_all(Person("Alex Morgan"))
    assert engine.search.call_count == 18
