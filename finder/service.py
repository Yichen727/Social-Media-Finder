"""Orchestrate each platform independently and preserve partial search failures."""

from finder.identity_matcher import rank_candidates
from finder.linkedin_profile import (
    build_detail_queries, populate_career_details, relaxed_profession, title_match_level,
)
from finder.models import MatchStatus, Person, Platform, PlatformResult, Query, QueryRun, utc_now
from finder.profile_parser import extract_candidates, normalize_profile_url
from finder.public_profile import build_metrics_query, populate_public_details
from finder.query_builder import build_queries, search_term
from finder.search_engine import DDGSSearchEngine, SearchProvider, classify_error


class FinderService:
    def __init__(self, engine: SearchProvider | None = None, verifier=None):
        self.engine = engine if engine is not None else DDGSSearchEngine()
        self.verifier = verifier

    def _run_query(self, query: Query) -> QueryRun:
        try:
            return self.engine.search(query)
        except Exception as exc:
            return QueryRun(query=query, error=classify_error(exc))

    def search_platform(self, person: Person, platform: Platform) -> PlatformResult:
        result = PlatformResult(platform=platform, searched_at=utc_now())
        for query in build_queries(person, platform):
            result.runs.append(self._run_query(query))
        hits = [hit for run in result.runs for hit in run.hits]
        candidates = extract_candidates(hits, platform)
        if platform == Platform.LINKEDIN:
            for candidate in candidates:
                populate_career_details(candidate, person)
            # Search indexes sometimes omit "Senior"/"Lead". A single relaxed
            # discovery query recovers the core role without inventing seniority.
            relaxed = relaxed_profession(person.profession)
            if relaxed and not any(title_match_level(person.profession, candidate.job_title) == "exact"
                                   for candidate in candidates):
                query = Query("LinkedIn role fallback",
                              f'site:linkedin.com/in/ "{search_term(person.full_name)}" {search_term(relaxed)}')
                result.runs.append(self._run_query(query))
                hits = [hit for run in result.runs for hit in run.hits]
                candidates = extract_candidates(hits, platform)
                for candidate in candidates:
                    populate_career_details(candidate, person)
            if person.profession or person.organization:
                for query in build_detail_queries(person, candidates):
                    result.runs.append(self._run_query(query))
                hits = [hit for run in result.runs for hit in run.hits]
                candidates = extract_candidates(hits, platform)
        if self.verifier is not None:
            try:
                result.verification_notes = self.verifier.verify(person, candidates, hits)
            except Exception as exc:
                result.verification_notes.append(f"Public reference check unavailable: {type(exc).__name__}: {str(exc)[:180]}")
        result.candidates = rank_candidates(candidates, person)
        for candidate in result.candidates:
            populate_public_details(candidate, person)
        # A small, per-platform budget fills follower fields omitted by discovery.
        # Only results for the exact profile may enrich that candidate.
        for candidate in [item for item in result.candidates if item.follower_count is None][:2]:
            run = self._run_query(build_metrics_query(person, candidate))
            result.runs.append(run)
            for hit in run.hits:
                parsed = normalize_profile_url(hit.url)
                if parsed and parsed[1] == candidate.url and hit not in candidate.hits:
                    candidate.hits.append(hit)
            populate_public_details(candidate, person)
        # New index text may reveal career context or a fan/parody account.
        result.candidates = rank_candidates(result.candidates, person)
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
