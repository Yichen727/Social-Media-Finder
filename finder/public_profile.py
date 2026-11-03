"""Read explicitly indexed public profile metrics without guessing missing facts."""

from dataclasses import dataclass
from decimal import Decimal
import re

from finder.identity_matcher import contains_name
from finder.models import Candidate, Person, Platform, Query
from finder.profile_parser import normalize_profile_url
from finder.query_builder import search_term

NUMBER = r"(?:\d{1,3}(?:[,\u00a0\u202f ]\d{3})+|\d+)(?:\.\d+)?"
UNIT = r"(?:thousand|million|billion|[kmb]|万|亿)"
QUANTITY = rf"(?P<number>{NUMBER})\s*(?P<unit>{UNIT})?\s*(?P<plus>\+)?"
FOLLOWERS_AFTER = re.compile(rf"(?<![\w.,]){QUANTITY}\s*(?:followers\b|粉丝)", re.I)
FOLLOWERS_BEFORE = re.compile(rf"\bfollowers\s*[:：]\s*{QUANTITY}(?![\w.,])", re.I)
SCALES = {"": 1, "k": 1000, "thousand": 1000, "m": 1000000,
          "million": 1000000, "b": 1000000000, "billion": 1000000000,
          "万": 10000, "亿": 100000000}


@dataclass(frozen=True)
class FollowerCount:
    count: int
    display: str
    note: str


def parse_followers(text: str, platform: Platform | None = None) -> FollowerCount | None:
    """Read explicit counts, excluding metrics attributed to another platform."""
    labels = {Platform.INSTAGRAM: {"instagram"}, Platform.X: {"twitter", "x"},
              Platform.LINKEDIN: {"linkedin"}}
    for pattern in (FOLLOWERS_AFTER, FOLLOWERS_BEFORE):
        for match in pattern.finditer(text):
            other = re.match(r"\s+(?:on\s+)?(instagram|twitter|x|tiktok|youtube|facebook|linkedin)\b",
                             text[match.end():], re.I)
            if platform and other and other[1].lower() not in labels[platform]:
                continue
            number = Decimal(re.sub(r"[,\u00a0\u202f ]", "", match["number"]))
            unit = (match["unit"] or "").lower()
            value = number * SCALES[unit]
            if value != value.to_integral_value():
                continue
            note = "Rounded" if unit else "Indexed count"
            prefix = text[max(0, match.start() - 24):match.start()]
            modifier = re.search(r"\b(over|more than|at least|about|approximately|around)\s*$", prefix, re.I)
            if match["plus"] or modifier and modifier[1].lower() in {"over", "more than", "at least"}:
                note = "Lower bound"
            elif modifier:
                note = "Approximate"
            display = match["number"] + (match["unit"] or "") + (match["plus"] or "")
            if modifier:
                display = modifier[1] + " " + display
            return FollowerCount(int(value), display, note)
    return None


def profile_introduction(text: str, full_name: str) -> str:
    """Stop before activity or concatenated neighboring profile results."""
    text = re.split(
        r"\b(?:Activity|Recommendations|People also viewed|Others named|Liked by|Reposted by|Shared by)\s*:?",
        text, maxsplit=1, flags=re.I
    )[0]
    name_pattern = r"\s+".join(re.escape(part) for part in full_name.split())
    text = re.split(rf"\bView\s+{name_pattern}[’']s?\s+profile", text, maxsplit=1, flags=re.I)[0]
    names = list(re.finditer(name_pattern, text, flags=re.I))
    if len(names) > 1:
        text = text[:names[1].start()]
    return text[:700]


def populate_public_details(candidate: Candidate, person: Person) -> Candidate:
    candidate.nationality = candidate.nationality_source = ""
    if candidate.platform != Platform.LINKEDIN:
        candidate.headline = candidate.job_title = candidate.company = ""
        candidate.professional_evidence = []
    candidate.follower_count = None
    candidate.follower_display = candidate.follower_note = candidate.follower_source = ""
    for hit in candidate.hits:
        parsed = normalize_profile_url(hit.url)
        if not parsed or parsed[1] != candidate.url:
            continue
        # Metrics lookups may expose only the handle in the indexed title.
        handle_title = candidate.platform != Platform.LINKEDIN and re.search(
            rf"(?<![\w@])@{re.escape(candidate.handle)}(?!\w)", hit.title, re.I
        )
        if not contains_name(hit.title, person.full_name) and not handle_title:
            continue
        intro = profile_introduction(hit.snippet, person.full_name)
        if candidate.platform == Platform.X:
            # Read the account header, stopping before timeline/recommendation content.
            intro = re.split(
                r"(?:^|\n)\s*(?:Posts|Replies|Media|Highlights|Pinned|Relevant people|Who to follow|You might like)\s*(?:\n|$)",
                intro, maxsplit=1, flags=re.I,
            )[0]
        count = parse_followers(intro if candidate.platform == Platform.X else intro[:400], candidate.platform)
        if count and (candidate.follower_count is None
                      or count.note == "Indexed count" and candidate.follower_note != "Indexed count"):
            candidate.follower_count = count.count
            candidate.follower_display = count.display
            candidate.follower_note = count.note
            candidate.follower_source = hit.url
    return candidate


def build_metrics_query(person: Person, candidate: Candidate, fallback: int = 0) -> Query:
    if candidate.platform == Platform.X:
        scopes = (f"site:x.com/{candidate.handle}", "site:x.com")
        scope = scopes[fallback]
        query = f'{scope} "Followers"' if fallback != 1 else f'{scope} "{candidate.handle}" "Followers"'
    elif candidate.platform == Platform.INSTAGRAM:
        scopes = (f"site:instagram.com/{candidate.handle}", "site:instagram.com")
        scope = scopes[fallback]
        query = f'{scope} "Followers"' if not fallback else f'{scope} "{candidate.handle}" "Followers"'
    else:
        scope = candidate.url.removeprefix("https://").removeprefix("www.")
        query = f'site:{scope} "{search_term(person.full_name)}" followers'
    return Query("Public profile metrics", query)
