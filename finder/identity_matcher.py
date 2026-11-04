"""Conservative profile ranking using name, career and reference evidence."""

import re
import unicodedata

from finder.models import Candidate, Evidence, MatchStatus, Person, Platform


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


def words(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", normalized(value), re.UNICODE)


def contains_name(text: str, name: str) -> bool:
    # Whole, contiguous name tokens: Emma Watson must not match Emily Watson.
    target = " ".join(words(name))
    return bool(target) and f" {target} " in f" {' '.join(words(text))} "


def has_fan_signal(text: str) -> bool:
    return bool(re.search(r"\b(?:fan\s*(?:account|page|club)|fans|parody|unofficial|"
                          r"impersonat\w*|tribute\s*(?:account|page))\b", text, re.I))


def rank_candidate(candidate: Candidate, person: Person) -> Candidate:
    from finder.linkedin_profile import populate_career_details, title_match_level
    if candidate.platform == Platform.LINKEDIN:
        populate_career_details(candidate, person)
    else:
        person = Person(person.full_name)
        candidate.job_title = candidate.company = ""
        candidate.professional_evidence = []
    candidate.evidence = [e for e in candidate.evidence if e.strength == "strong"]
    score = 0
    title_match = any(contains_name(hit.title, person.full_name) for hit in candidate.hits)
    snippet_match = any(contains_name(hit.snippet, person.full_name) for hit in candidate.hits)
    compact_name = "".join(words(person.full_name))
    compact_handle = "".join(words(candidate.handle))
    handle_match = compact_name == compact_handle
    source = candidate.hits[0].url if candidate.hits else candidate.url
    if title_match:
        score += 40
        candidate.evidence.append(Evidence("The indexed profile title contains the full name.", source))
    if handle_match:
        score += 15
        candidate.evidence.append(Evidence("The handle matches the name after punctuation is removed.", source))
    if snippet_match:
        score += 8
        candidate.evidence.append(Evidence("A search snippet contains the full name.", source))
    text = " ".join(f"{hit.title} {hit.snippet}" for hit in candidate.hits)
    for label, value in (("Profession", person.profession), ("Organization", person.organization)):
        if value and contains_name(text, value):
            score += 8
            candidate.evidence.append(Evidence(f"{label} appears in the indexed text: {value}.", source))
    # A structured, profile-attributed role/company outweighs a namesake's neat handle.
    # Career context improves identity ranking, never the ownership/officialness gate.
    if person.profession and candidate.job_title:
        role_match = title_match_level(person.profession, candidate.job_title)
        if role_match:
            score += 48 if role_match == "exact" else 32
            candidate.evidence.extend(
                evidence for evidence in candidate.professional_evidence
                if evidence.description.startswith("Job title")
            )
    if person.organization and candidate.company and contains_name(candidate.company, person.organization):
        score += 28
        candidate.evidence.extend(
            evidence for evidence in candidate.professional_evidence
            if evidence.description.startswith("Company")
        )
    strong = {e.source_url for e in candidate.evidence if e.strength == "strong"}
    score += min(len(strong), 2) * 25
    fan = has_fan_signal(text) or bool(re.search(r"(?:fanpage|fanclub|parody|unofficial)", candidate.handle, re.I))
    for hit in candidate.hits:
        title_words = " ".join(words(hit.title))
        name_words = " ".join(words(person.full_name))
        if re.search(rf"\b{re.escape(name_words)}\s+(?:news|updates?|archives?|fans?|daily|fanpage)\b", title_words):
            fan = True
    if compact_handle in {compact_name + suffix for suffix in ("fan", "fans", "daily", "news", "updates", "archive", "archives")}:
        fan = True
    if fan:
        score -= 100
    identity_supported = title_match or (handle_match and snippet_match) or bool(strong)
    if not identity_supported:
        score = min(score, 10)
    candidate.score = score
    # Two separately fetched reference domains are required; self-described 'official'
    # wording and search ranking never qualify as strong evidence.
    from urllib.parse import urlsplit
    from finder.public_evidence import reference_family
    families = {reference_family(urlsplit(url).hostname or "") for url in strong}
    families.discard(None)
    if len(families) >= 2 and identity_supported and not fan:
        candidate.status = MatchStatus.LIKELY
    else:
        candidate.status = MatchStatus.POSSIBLE
    return candidate


def rank_candidates(candidates: list[Candidate], person: Person) -> list[Candidate]:
    ranked = [rank_candidate(candidate, person) for candidate in candidates]
    # Keep namesakes and self-described fan accounts for user comparison.
    # A matching name/handle is required; merely mentioning the person is insufficient.
    relevant = [candidate for candidate in ranked
                if candidate.score >= 35
                or any(contains_name(hit.title, person.full_name) for hit in candidate.hits)
                or "".join(words(candidate.handle)) == "".join(words(person.full_name))]
    return sorted(relevant, key=lambda candidate: (-candidate.score, candidate.url))
