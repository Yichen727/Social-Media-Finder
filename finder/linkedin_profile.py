"""Extract attributable LinkedIn career details from public search-index text.

No LinkedIn HTTP requests, login sessions, or guessed professional details.
"""

import re
from dataclasses import dataclass

from finder.models import Candidate, Evidence, Person, Platform, Query, SearchHit
from finder.profile_parser import normalize_profile_url
from finder.query_builder import search_term

ROLE_WORDS = re.compile(
    r"\b(?:producer|director|manager|engineer|developer|designer|consultant|analyst|"
    r"scientist|researcher|professor|lecturer|officer|president|ceo|cfo|cto|coo|"
    r"founder|partner|editor|writer|actor|actress|athlete|architect|lawyer|"
    r"accountant|specialist|coordinator|strategist|executive|head|lead|chief|"
    r"photographer|adviser|advisor|professional|artist|musician|technician)\b", re.I
)
NON_PERSONAL = re.compile(
    r"\b(?:professional profile|followers|connections|join linkedin|view profile|"
    r"united kingdom|united states|greater .+ area|metropolitan area)\b", re.I
)
NO_ROLE = re.compile(
    r"\b(?:hiring|vacancy|vacancies|seeking|looking for|recruiting|jobs?|"
    r"formerly|previously|former|past roles?|ex[- ]|opportunities|recommendations?|liked|"
    r"shared|reposted|commented|mentions?|worked with)\b", re.I
)
SECTION_BREAK = re.compile(r"\b(?:Experience|Education|Activity|Recommendations)\s*:", re.I)


@dataclass(frozen=True)
class CareerDetails:
    headline: str = ""
    job_title: str = ""
    company: str = ""


def clean(value: str) -> str:
    return " ".join(value.split()).strip(" .·|–—-")


def is_role(value: str) -> bool:
    return (bool(ROLE_WORDS.search(value)) and not NO_ROLE.search(value)
            and not NON_PERSONAL.search(value) and 2 <= len(value) <= 110
            and len(value.split()) <= 16
            and "..." not in value and "…" not in value
            and not re.search(r"\b(?:ltd|limited|inc|llp|llc|studios)\b", value, re.I))


def clean_company(value: str) -> str:
    value = re.split(r"\s+[|·/]\s+|\s+[-–—]\s+(?:Location|Education|Experience)\s*:", value)[0]
    if "..." in value or "…" in value:
        return ""
    value = clean(value)
    if (not value or len(value) > 120 or NON_PERSONAL.search(value)
            or NO_ROLE.search(value) or "..." in value or "…" in value
            or re.search(r"\b(?:Present|years?|months?)\b|\d{4}\s*[-–—]", value, re.I)):
        return ""
    return value


def split_headline(value: str) -> CareerDetails:
    truncated = "..." in value or "…" in value
    value = clean(value)
    if not value or NO_ROLE.search(value):
        return CareerDetails()
    parts = re.split(r"\s+(?:at|@)\s+|\s+[|]\s+", value, maxsplit=1, flags=re.I)
    role = clean(parts[0])
    if truncated and len(parts) == 1:
        return CareerDetails()
    if is_role(role):
        company = clean_company(parts[1]) if len(parts) == 2 and not truncated else ""
        headline = value if not truncated else ""
        return CareerDetails(headline, role, company)
    return CareerDetails()


def extract_career_details(hit: SearchHit, full_name: str) -> CareerDetails:
    """Use profile-title/headline segments, not jobs mentioned in activity text."""
    from finder.identity_matcher import contains_name

    if not normalize_profile_url(hit.url) or normalize_profile_url(hit.url)[0] != Platform.LINKEDIN:
        return CareerDetails()
    name_pattern = r"\s+".join(re.escape(part) for part in full_name.split())
    title = re.split(r"\s*\|\s*LinkedIn", hit.title, maxsplit=1, flags=re.I)[0]
    # Several DDGS backends concatenate adjacent result titles. Only the first
    # person's title is attributable to this URL.
    repeats = list(re.finditer(name_pattern, title, re.I))
    if len(repeats) > 1:
        title = title[:repeats[1].start()]
    parts = re.split(r"\s+[-–—]\s+", title, maxsplit=1)
    if not parts or not contains_name(parts[0], full_name):
        return CareerDetails()
    tail = parts[1].strip() if len(parts) > 1 else ""
    details = split_headline(tail)
    company = details.company
    if tail and not details.job_title and not is_role(tail):
        # A short "Name - Organization | LinkedIn" title identifies an indexed company.
        company = clean_company(tail) if (
            "," not in tail and not re.search(r"\b(?:working|helping|building|driving|delivering|passionate)\b", tail, re.I)
        ) else ""

    # The profile's introduction precedes activity, experience history and education.
    snippet = re.split(
        r"\b(?:Activity|Recommendations|People also viewed|Others named|"
        r"Liked by|Reposted by|Shared by)\b", hit.snippet, maxsplit=1, flags=re.I
    )[0]
    snippet = re.split(rf"\bView\s+{name_pattern}[’']s?\s+profile", snippet,
                       maxsplit=1, flags=re.I)[0]
    introduction = SECTION_BREAK.split(snippet, maxsplit=1)[0]
    introduction = introduction[:500]
    introduction = re.sub(rf"^\s*{name_pattern}\s*[-–—:.,|·]*\s*", "", introduction, flags=re.I)
    # Inspect short leading segments only; do not scan arbitrary post text for a role.
    segments = re.split(r"\s+[·]\s+|\n|;|\.\s+(?=[A-Z])", introduction)
    for segment in segments[:2]:
        parsed = split_headline(segment)
        if (company and parsed.company
                and not contains_name(company, parsed.company)
                and not contains_name(parsed.company, company)):
            # Some provider snippets concatenate multiple results for namesakes.
            # A role attached to another company cannot enrich this profile.
            continue
        if parsed.job_title and (not details.job_title or not details.headline):
            details = parsed
        if parsed.company and not company:
            company = parsed.company
    # An explicit Experience label is an indexed affiliation, not proof of current employment.
    affiliation = re.search(r"\b(?:Current company|Company|Experience)\s*:\s*([^·|\n;]+)", snippet, re.I)
    if affiliation and not company and not NO_ROLE.search(snippet[:affiliation.start()]):
        company = clean_company(affiliation.group(1))
    return CareerDetails(details.headline, details.job_title, company)


def populate_career_details(candidate: Candidate, person: Person) -> Candidate:
    if candidate.platform != Platform.LINKEDIN:
        return candidate
    candidate.job_title = candidate.company = ""
    candidate.professional_evidence = []
    for hit in candidate.hits:
        details = extract_career_details(hit, person.full_name)
        for field in ("job_title", "company"):
            value = getattr(details, field)
            if value and not getattr(candidate, field):
                setattr(candidate, field, value)
                label = {"job_title": "Job title", "company": "Company"}[field]
                candidate.professional_evidence.append(
                    Evidence(f"{label} from the public LinkedIn search index: {value}.", hit.url)
                )
    return candidate


def title_match_level(requested: str, indexed: str) -> str:
    """Recognize a missing seniority marker without claiming an exact title match."""
    from finder.identity_matcher import contains_name, words

    def role_tokens(value):
        aliases = {"sr": "senior", "jr": "junior"}
        return [aliases.get(token, token) for token in words(value)]

    expected, actual = role_tokens(requested), role_tokens(indexed)
    if not expected or not actual:
        return ""
    if contains_name(" ".join(actual), " ".join(expected)):
        return "exact"
    seniority = {"senior", "junior", "lead"}
    # Explicitly different seniority is a contradiction, not an omitted modifier.
    expected_level, actual_level = set(expected) & seniority, set(actual) & seniority
    if expected_level and actual_level and expected_level != actual_level:
        return ""
    expected_core = [token for token in expected if token not in seniority]
    actual_core = [token for token in actual if token not in seniority]
    if expected_core == actual_core:
        return "compatible"
    return ""


def relaxed_profession(value: str) -> str:
    from finder.identity_matcher import words
    tokens = [token for token in words(value) if token not in {"senior", "sr", "junior", "jr", "lead"}]
    result = " ".join(tokens)
    return result if result != " ".join(words(value)) else ""


def build_detail_queries(person: Person, candidates: list[Candidate]) -> list[Query]:
    """At most two exact-profile index lookups for the most relevant name matches."""
    from finder.identity_matcher import contains_name
    pool = [candidate for candidate in candidates if candidate.platform == Platform.LINKEDIN
            and any(contains_name(hit.title, person.full_name) for hit in candidate.hits)]
    pool.sort(key=lambda candidate: (
        not bool(person.profession and title_match_level(person.profession, candidate.job_title)),
        not bool(person.organization and contains_name(candidate.company, person.organization)),
        not bool(candidate.job_title or candidate.company),
        candidate.url,
    ))
    queries = []
    for candidate in pool[:2]:
        # Exact profile scope, not a repeated global search. Input context is never
        # copied into extracted metadata unless it also appears in the response.
        terms = " ".join(search_term(value) for value in (person.profession, person.organization) if value)
        text = f'site:linkedin.com/in/{candidate.handle} "{search_term(person.full_name)}"'
        if terms:
            text += " " + terms
        queries.append(Query("LinkedIn profile details", text))
    return queries
