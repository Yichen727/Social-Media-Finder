"""Replaceable DDGS adapter with bounded retries and honest failure states."""

import time
from collections.abc import Callable
from typing import Protocol

from finder.models import Query, QueryRun, SearchError, SearchHit


class SearchProvider(Protocol):
    def search(self, query: Query) -> QueryRun: ...


def classify_error(exc: Exception) -> SearchError:
    detail = f"{type(exc).__name__}: {exc}"
    lower = detail.lower()
    if any(word in lower for word in ("captcha", "challenge", "403", "forbidden", "blocked")):
        kind, message = "access", "The search provider restricted automated access. Try the manual search link."
    elif any(word in lower for word in ("ratelimit", "rate limit", "429", "too many requests", "202")):
        kind, message = "rate_limit", "The search provider is limiting requests. Wait before refreshing."
    elif isinstance(exc, TimeoutError) or any(word in lower for word in ("timeout", "timed out")):
        kind, message = "timeout", "The search provider timed out. Try again later."
    elif any(word in lower for word in ("certificate", "ssl", "tls")):
        kind, message = "tls", "A secure connection could not be established. Check your network or company proxy."
    elif any(word in lower for word in ("connect", "resolve", "dns", "network", "socket")):
        kind, message = "network", "The search provider could not be reached. Check your internet connection."
    elif any(word in lower for word in ("httperror", "httpstatuserror", "http error", "http status", "status code", "http 4", "http 5")):
        kind, message = "http", "The search provider returned an HTTP error. Try again later."
    else:
        kind, message = "provider", "The search provider could not complete this query. Try the manual search link."
    return SearchError(kind, message, detail[:2000])


class DDGSSearchEngine:
    def __init__(self, timeout: int = 8, max_results: int = 8, max_attempts: int = 2,
                 client_factory: Callable | None = None, sleep: Callable = time.sleep):
        self.timeout = timeout
        self.max_results = max_results
        self.max_attempts = min(3, max(1, max_attempts))
        self.client_factory = client_factory
        self.sleep = sleep

    def search(self, query: Query) -> QueryRun:
        for attempt in range(1, self.max_attempts + 1):
            try:
                factory = self.client_factory
                if factory is None:
                    from ddgs import DDGS
                    factory = DDGS
                client = factory(timeout=self.timeout)
                raw = client.text(query.text, backend="auto", max_results=self.max_results,
                                  safesearch="moderate", region="us-en")
                if raw is None:
                    raise RuntimeError("Search provider returned an invalid empty response.")
                hits = []
                for item in raw:
                    url = item.get("href") or item.get("url")
                    if url:
                        hits.append(SearchHit(str(item.get("title") or ""), str(url),
                                              str(item.get("body") or item.get("snippet") or "")))
                return QueryRun(query=query, hits=hits, attempts=attempt)
            except Exception as exc:
                # DDGS raises this exact signal when engines return no results and
                # no underlying error. Do not confuse it with wrapped HTTP/timeouts.
                if type(exc).__name__ == "DDGSException" and str(exc).strip() == "No results found.":
                    return QueryRun(query=query, attempts=attempt)
                error = classify_error(exc)
                # Do not repeatedly challenge a blocked provider or a broken TLS setup.
                if attempt == self.max_attempts or error.kind in {"access", "tls"}:
                    return QueryRun(query=query, error=error, attempts=attempt)
                self.sleep(0.8 * 2 ** (attempt - 1))
        raise AssertionError("Unreachable retry state")
