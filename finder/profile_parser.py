"""Strict, domain-aware profile extraction; never invent a handle."""

import re
from urllib.parse import parse_qs, unquote, urlsplit

from finder.models import Candidate, Platform, SearchHit

IG_RESERVED = {
    "p", "reel", "reels", "stories", "explore", "accounts", "about", "legal", "privacy",
    "terms", "developer", "developers", "directory", "web", "direct", "challenge",
    "emails", "oauth", "api", "static", "tv", "share", "hashtag", "hashtags",
}
X_RESERVED = {
    "home", "search", "explore", "hashtag", "hashtags", "i", "intent", "share", "login",
    "logout", "signup", "settings", "messages", "notifications", "compose", "tos",
    "privacy", "help", "about", "download", "jobs", "account", "who_to_follow",
}


def normalize_profile_url(raw: str) -> tuple[Platform, str, str] | None:
    try:
        parts = urlsplit(raw.strip())
        if parts.scheme not in {"https", "http"} or parts.username or parts.password:
            return None
        if parts.port not in {None, 80, 443}:
            return None
        host = (parts.hostname or "").lower().rstrip(".")
        if host in {"duckduckgo.com", "www.duckduckgo.com"} and parts.path in {"/l/", "/l"}:
            target = parse_qs(parts.query).get("uddg", [""])[0]
            # Unwrap exactly one known redirect; reject nested redirects.
            if "duckduckgo.com" not in (urlsplit(target).hostname or ""):
                return normalize_profile_url(target)
            return None
        path = unquote(parts.path)
        segments = path.strip("/").split("/")
        if "//" in path or any(not segment for segment in segments):
            return None
        if host == "linkedin.com" or host.endswith(".linkedin.com"):
            if len(segments) == 2 and segments[0].lower() == "in":
                handle = segments[1].lower()
                if re.fullmatch(r"[\w-]{1,100}", handle, re.UNICODE):
                    return Platform.LINKEDIN, f"https://www.linkedin.com/in/{handle}/", handle
        if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
            if len(segments) == 1 or (len(segments) == 2 and segments[1] in {"reels", "tagged"}):
                handle = segments[0].lower()
                if (handle not in IG_RESERVED and re.fullmatch(r"[a-z0-9_.]{1,30}", handle)
                        and not handle.startswith(".") and not handle.endswith(".") and ".." not in handle):
                    return Platform.INSTAGRAM, f"https://www.instagram.com/{handle}/", handle
        if host in {"x.com", "www.x.com", "mobile.x.com", "m.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com", "m.twitter.com"}:
            # These tabs retain the account header; posts and follower lists do not qualify.
            if len(segments) == 1 or (len(segments) == 2 and segments[1] in {"with_replies", "media", "highlights", "reposts"}):
                handle = segments[0].lower()
                if handle not in X_RESERVED and re.fullmatch(r"[a-z0-9_]{1,15}", handle):
                    return Platform.X, f"https://x.com/{handle}", handle
    except (ValueError, TypeError):
        return None
    return None


def extract_candidates(hits: list[SearchHit], platform: Platform) -> list[Candidate]:
    by_url: dict[str, Candidate] = {}
    for hit in hits:
        parsed = normalize_profile_url(hit.url)
        if not parsed or parsed[0] != platform:
            continue
        _, url, handle = parsed
        if url not in by_url:
            # This is the indexed title, not an independently fetched display name.
            name = re.split(r"\s+[|–—-]\s+", hit.title)[0].strip()
            by_url[url] = Candidate(platform=platform, url=url, handle=handle, profile_name=name)
        if hit not in by_url[url].hits:
            by_url[url].hits.append(hit)
    return list(by_url.values())
