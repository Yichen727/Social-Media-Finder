"""Orchestrate each platform independently and preserve partial search failures."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore
from time import monotonic

from finder.identity_matcher import rank_candidates
from finder.linkedin_profile import (
    build_detail_queries, populate_career_details, relaxed_profession, title_match_level,
)
from finder.models import Candidate, MatchStatus, Person, Platform, PlatformResult, Query, QueryRun, SearchError, utc_now
from finder.profile_parser import extract_candidates, normalize_profile_url
from finder.public_profile import build_metrics_query, populate_public_details
from finder.query_builder import build_queries, search_term
from finder.search_engine import DDGSSearchEngine, SearchProvider, classify_error


class FinderService:
    def __init__(self, engine: SearchProvider | None = None, verifier=None, follower_cache: dict | None = None, metrics_budget: float = 12):
        self.engine = engine if engine is not None else DDGSSearchEngine(timeout=8, max_attempts=1)
        self.verifier = verifier
        self.follower_cache = follower_cache if follower_cache is not None else {}
        self.metrics_budget = metrics_budget
        self._network_slots = BoundedSemaphore(3)

    def _run_query(self, query: Query) -> QueryRun:
        try:
            with self._network_slots:
                return self.engine.search(query)
        except Exception as exc:
            return QueryRun(query=query, error=classify_error(exc))

    def search_platform(self, person: Person, platform: Platform) -> PlatformResult:
        result = PlatformResult(platform=platform, searched_at=utc_now())
        if platform != Platform.LINKEDIN:
            person = Person(person.full_name)
        result.runs.extend(self._run_queries(build_queries(person, platform)))
        hits = [hit for run in result.runs for hit in run.hits]
        candidates = extract_candidates(hits, platform)
        if platform != Platform.LINKEDIN and not candidates and all(run.error for run in result.runs):
            # One recovery attempt for a complete provider failure, not a retry per query.
            scope = "site:instagram.com" if platform == Platform.INSTAGRAM else "site:x.com"
            result.runs.append(self._run_query(Query("Discovery retry",
                f'{scope} "{search_term(person.full_name)}" "Followers"')))
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
                result.runs.extend(self._run_queries(build_detail_queries(person, candidates)))
                hits = [hit for run in result.runs for hit in run.hits]
                candidates = extract_candidates(hits, platform)
        if platform != Platform.LINKEDIN:
            # Excluding the leading profiles gives less prominent namesakes a chance.
            scope = "site:instagram.com" if platform == Platform.INSTAGRAM else "site:x.com"
            exclusions = " ".join(f"-inurl:{candidate.handle}" for candidate in candidates[:3])
            query = Query("More same-name profiles",
                          f'{scope} "{search_term(person.full_name)}" "Followers" {exclusions}'.strip())
            if all(run.query.text != query.text for run in result.runs):
                result.runs.append(self._run_query(query))
                hits = [hit for run in result.runs for hit in run.hits]
                candidates = extract_candidates(hits, platform)
        if platform == Platform.LINKEDIN and self.verifier is not None:
            try:
                result.verification_notes = self.verifier.verify(person, candidates, hits)
            except Exception as exc:
                result.verification_notes.append(f"Public reference check unavailable: {type(exc).__name__}: {str(exc)[:180]}")
        result.candidates = rank_candidates(candidates, person)
        for candidate in result.candidates:
            populate_public_details(candidate, person)
        self.fill_missing_followers(person, result, budget=self.metrics_budget)
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

    def _run_queries(self, queries: list[Query]) -> list[QueryRun]:
        if not queries:
            return []
        with ThreadPoolExecutor(max_workers=3) as pool:
            return list(pool.map(self._run_query, queries))

    def fill_missing_followers(self, person: Person, result: PlatformResult, budget: float | None = None):
        """Use cached observations first; a manual fill can run without a time budget."""
        result.runs = [run for run in result.runs if not (run.error and run.error.kind == "budget")]
        self._remember_followers(result.candidates, reuse_only=True)
        deadline = monotonic() + budget if budget is not None else None
        attempts = {Platform.LINKEDIN: 1, Platform.INSTAGRAM: 2, Platform.X: 2}
        for fallback in range(attempts[result.platform]):
            missing = [candidate for candidate in result.candidates if candidate.follower_count is None]
            if not missing or deadline is not None and monotonic() >= deadline:
                break
            with ThreadPoolExecutor(max_workers=3) as pool:
                runs = pool.map(lambda candidate: self._lookup_followers(person, candidate, fallback, deadline), missing)
                round_runs = [run for run in runs if run is not None]
                result.runs.extend(round_runs)
            if any(run.error and run.error.kind in {"access", "rate_limit", "tls"}
                   for run in round_runs):
                break
        if deadline is not None and monotonic() >= deadline and any(c.follower_count is None for c in result.candidates):
            result.runs.append(QueryRun(Query("Follower lookup budget", ""), error=SearchError(
                "budget", "Some follower lookups were deferred. Use Fill missing Followers to continue.",
                "The initial follower lookup budget was reached; account rows are preserved.")))
        self._remember_followers(result.candidates)

    def _lookup_followers(self, person, candidate, fallback, deadline):
        # Check again after acquiring a slot so queued work cannot outlive the budget.
        with self._network_slots:
            if deadline is not None and monotonic() >= deadline:
                return None
            query = build_metrics_query(person, candidate, fallback=fallback)
            try:
                run = self.engine.search(query)
            except Exception as exc:
                run = QueryRun(query, error=classify_error(exc))
        for hit in run.hits:
            parsed = normalize_profile_url(hit.url)
            if parsed and parsed[1] == candidate.url and hit not in candidate.hits:
                candidate.hits.append(hit)
        populate_public_details(candidate, person)
        return run

    def _remember_followers(self, candidates: list[Candidate], reuse_only: bool = False):
        now = datetime.now(timezone.utc)
        fields = ("follower_count", "follower_display", "follower_note", "follower_source")
        for candidate in candidates:
            if candidate.follower_count is not None:
                if reuse_only or candidate.follower_observed_at:
                    continue
                candidate.follower_observed_at = now.isoformat(timespec="seconds")
                self.follower_cache[candidate.url] = {
                    **{field: getattr(candidate, field) for field in fields},
                    "follower_observed_at": candidate.follower_observed_at,
                }
            else:
                saved = self.follower_cache.get(candidate.url)
                if not saved or now - datetime.fromisoformat(saved["follower_observed_at"]) > timedelta(hours=24):
                    continue
                for field, value in saved.items():
                    setattr(candidate, field, value)
                candidate.follower_note += f"; Earlier observation ({candidate.follower_observed_at})"

    def search_selected(self, person: Person, platforms):
        platforms = list(dict.fromkeys(platforms))
        if not platforms:
            return
        with ThreadPoolExecutor(max_workers=len(platforms)) as pool:
            pending = {pool.submit(self.search_platform, person, platform): platform for platform in platforms}
            for future in as_completed(pending):
                yield future.result()

    def search_all(self, person: Person) -> list[PlatformResult]:
        results = {result.platform: result for result in self.search_selected(person, Platform)}
        return [results[platform] for platform in Platform]
