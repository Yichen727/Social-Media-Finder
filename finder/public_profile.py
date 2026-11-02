"""Read explicitly indexed public profile metrics without guessing missing facts."""

from dataclasses import dataclass
from decimal import Decimal
import re

from finder.identity_matcher import contains_name
from finder.linkedin_profile import split_headline
from finder.models import Candidate, Evidence, Person, Platform, Query
from finder.profile_parser import normalize_profile_url
from finder.query_builder import search_term

NUMBER = r"(?:\d{1,3}(?:[,\u00a0\u202f ]\d{3})+|\d+)(?:\.\d+)?"
UNIT = r"(?:thousand|million|billion|[kmb]|万|亿)"
QUANTITY = rf"(?P<number>{NUMBER})\s*(?P<unit>{UNIT})?\s*(?P<plus>\+)?"
FOLLOWERS_AFTER = re.compile(rf"(?<![\w.,]){QUANTITY}\s*(?:followers\b|粉丝)", re.I)
FOLLOWERS_BEFORE = re.compile(rf"\bfollowers\s*[:：]\s*{QUANTITY}(?![\w.,])", re.I)
NATIONALITY = re.compile(
    r"\b(?:Nationality|Citizenship)(?:\s*/\s*(?:Nationality|Citizenship))?\s*[:：]\s*"
    r"([^\n·|;.!?]{2,80})", re.I
)
SCALES = {"": 1, "k": 1000, "thousand": 1000, "m": 1000000,
          "million": 1000000, "b": 1000000000, "billion": 1000000000,
          "万": 10000, "亿": 100000000}


@dataclass(frozen=True)
class FollowerCount:
    count: int
    display: str
    note: str


def parse_followers(text: str) -> FollowerCount | None:
    """Parse follower counts only; following, likes and connections do not qualify."""
    for pattern in (FOLLOWERS_AFTER, FOLLOWERS_BEFORE):
        match = pattern.search(text)
        if not match:
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
    candidate.follower_count = None
    candidate.follower_display = candidate.follower_note = candidate.follower_source = ""
    for hit in candidate.hits:
        parsed = normalize_profile_url(hit.url)
        if (not parsed or parsed[1] != candidate.url
                or not contains_name(hit.title, person.full_name)):
            continue
        intro = profile_introduction(hit.snippet, person.full_name)
        count = parse_followers(intro[:400])
        if count and (candidate.follower_count is None
                      or count.note == "Indexed count" and candidate.follower_note != "Indexed count"):
            candidate.follower_count = count.count
            candidate.follower_display = count.display
            candidate.follower_note = count.note
            candidate.follower_source = hit.url
        nationality = NATIONALITY.search(intro)
        if nationality and not candidate.nationality:
            value = nationality[1].strip(" ,")
            value = re.split(r"\s+(?:Location|Country|Company|Profession|Followers)\s*:", value, flags=re.I)[0].strip(" ,")
            if "..." not in value and "…" not in value and not any(char.isdigit() for char in value):
                candidate.nationality, candidate.nationality_source = value, hit.url
        # Other platforms occasionally expose an explicit role/company in the bio.
        if candidate.platform != Platform.LINKEDIN:
            for segment in re.split(r"[\n·;]|(?<=[.!?])\s+", intro)[:4]:
                name_pattern = r"\s+".join(re.escape(part) for part in person.full_name.split())
                segment = re.sub(rf"^\s*{name_pattern}(?:\s*\(@[^)]+\))?\s*[-–—:|]*\s*", "", segment, flags=re.I)
                segment = re.sub(r"^\s*(?:Bio|About|Headline)\s*:\s*", "", segment, flags=re.I)
                career = split_headline(segment.strip())
                if career.job_title and not candidate.job_title:
                    candidate.job_title = career.job_title
                    candidate.headline = career.headline
                    candidate.professional_evidence.append(Evidence(
                        f"Job title from the public profile search index: {career.job_title}.", hit.url))
                if career.company and not candidate.company:
                    candidate.company = career.company
                    candidate.professional_evidence.append(Evidence(
                        f"Company from the public profile search index: {career.company}.", hit.url))
    return candidate


def build_metrics_query(person: Person, candidate: Candidate) -> Query:
    scope = candidate.url.removeprefix("https://").removeprefix("www.")
    return Query("Public profile metrics",
                 f'site:{scope} "{search_term(person.full_name)}" followers')
