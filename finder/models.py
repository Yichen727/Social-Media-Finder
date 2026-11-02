"""Shared data contracts; no UI or search-provider dependencies."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Platform(str, Enum):
    LINKEDIN = "LinkedIn"
    INSTAGRAM = "Instagram"
    X = "X / Twitter"


class MatchStatus(str, Enum):
    LIKELY = "Likely Official"
    POSSIBLE = "Possible Match"
    NONE = "No Reliable Match"
    FAILED = "Search Failed"
    NOT_SEARCHED = "Not Searched"


@dataclass(frozen=True)
class Person:
    full_name: str
    profession: str = ""
    organization: str = ""
    country: str = ""

    def __post_init__(self):
        for name in ("full_name", "profession", "organization", "country"):
            value = " ".join(getattr(self, name).split())
            if len(value) > 160:
                raise ValueError("Please keep each field to 160 characters or fewer.")
            object.__setattr__(self, name, value)
        if not self.full_name or not any(char.isalpha() for char in self.full_name):
            raise ValueError("Enter a full name containing at least one letter.")


@dataclass(frozen=True)
class Query:
    stage: str
    text: str


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchError:
    kind: str
    message: str
    detail: str


@dataclass
class QueryRun:
    query: Query
    hits: list[SearchHit] = field(default_factory=list)
    error: SearchError | None = None
    attempts: int = 1


@dataclass(frozen=True)
class Evidence:
    description: str
    source_url: str
    strength: str = "weak"


@dataclass
class Candidate:
    platform: Platform
    url: str
    handle: str
    profile_name: str = ""
    hits: list[SearchHit] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    score: int = 0
    status: MatchStatus = MatchStatus.POSSIBLE
    confidence: str = "Low"
    headline: str = ""
    job_title: str = ""
    company: str = ""
    professional_evidence: list[Evidence] = field(default_factory=list)


@dataclass
class PlatformResult:
    platform: Platform
    status: MatchStatus = MatchStatus.NOT_SEARCHED
    candidates: list[Candidate] = field(default_factory=list)
    runs: list[QueryRun] = field(default_factory=list)
    verification_notes: list[str] = field(default_factory=list)
    searched_at: str = ""

    @property
    def errors(self) -> list[SearchError]:
        return [run.error for run in self.runs if run.error is not None]

    @property
    def partial(self) -> bool:
        return bool(self.errors) and any(run.error is None for run in self.runs)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
