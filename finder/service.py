"""Orchestrate each platform independently and preserve partial search failures."""

from finder.identity_matcher import rank_candidates
from finder.models import MatchStatus, Person, Platform, PlatformResult, QueryRun, utc_now
from finder.profile_parser import extract_candidates
from finder.query_builder import build_queries
from finder.search_engine import DDGSSearchEngine, SearchProvider, classify_error


class FinderService:
    def __init__(self, engine: SearchProvider | None = None, verifier=None):
        self.engine = engine if engine is not None else DDGSSearchEngine()
        self.verifier = verifier

    def search_platform(self, person: Person, platform: Platform) -> PlatformResult:
        result = PlatformResult(platform=platform, searched_at=utc_now())
        for query in build_queries(person, platform):
            try:
                result.runs.append(self.engine.search(query))
            except Exception as exc:
                result.runs.append(QueryRun(query=query, error=classify_error(exc)))
        hits = [hit for run in result.runs for hit in run.hits]
        candidates = extract_candidates(hits, platform)
        if self.verifier is not None:
            try:
                result.verification_notes = self.verifier.verify(person, candidates, hits)
            except Exception as exc:
                result.verification_notes.append(f"Public reference check unavailable: {type(exc).__name__}: {str(exc)[:180]}")
        result.candidates = rank_candidates(candidates, person)
        if result.candidates:
            result.status = result.candidates[0].status
        elif result.errors:
            # Even one failed query can hide the real candidate. Never call this absence.
            result.status = MatchStatus.FAILED
        else:
            result.status = MatchStatus.NONE
        return result

    def search_all(self, person: Person) -> list[PlatformResult]:
        return [self.search_platform(person, platform) for platform in Platform]
