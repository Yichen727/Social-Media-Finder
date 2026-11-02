"""Optional, tightly bounded corroboration on known public reference domains.

No arbitrary URLs, social pages, login, CAPTCHAs, or automatic redirects.
"""

from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from finder.models import Candidate, Evidence, Person, SearchHit
from finder.profile_parser import normalize_profile_url

# A small explicit source policy, not a claim that these sources know every person.
# Domain families are counted once (bbc.com and bbc.co.uk are the same source).
REFERENCE_DOMAINS = {
    "bbc.com": "bbc", "bbc.co.uk": "bbc", "reuters.com": "reuters",
    "apnews.com": "ap", "olympics.com": "olympics", "un.org": "un",
    "europa.eu": "europa", "gov.uk": "uk-government",
}
USER_AGENT = "SocialMediaFinder/1.0 (public reference verification)"


def reference_family(host: str) -> str | None:
    host = host.lower()
    for domain, family in REFERENCE_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return family
    return None


def safe_reference_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and not parts.username and not parts.password
                and parts.port in {None, 443} and bool(reference_family(parts.hostname or "")))
    except ValueError:
        return False


class PublicEvidenceVerifier:
    def __init__(self, session=None, page_budget: int = 2):
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.page_budget = min(2, max(0, page_budget))
        self.robots: dict[str, RobotFileParser | None] = {}

    def _read(self, url: str, robots: bool = False) -> tuple[int, str]:
        if not safe_reference_url(url):
            raise ValueError("Reference URL is outside the public source policy.")
        with self.session.get(url, headers={"User-Agent": USER_AGENT}, timeout=(3, 4),
                              allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                return response.status_code, ""
            content_type = response.headers.get("Content-Type", "").lower()
            if not robots and "html" not in content_type:
                raise ValueError("Reference response is not an HTML page.")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                data.extend(chunk)
                if len(data) > 524288:
                    raise ValueError("Reference page exceeds the 512 KB reading limit.")
            return 200, bytes(data).decode(response.encoding or "utf-8", errors="replace")

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            status, body = self._read(origin + "/robots.txt", robots=True)
            parser = RobotFileParser()
            if status == 404:
                parser.parse(["User-agent: *", "Allow: /"])
            elif status == 200:
                parser.parse(body.splitlines())
            else:
                self.robots[origin] = None
                return False
            self.robots[origin] = parser
        parser = self.robots[origin]
        # Avoid sites asking for paced crawling; this MVP does not schedule crawls.
        return bool(parser and parser.can_fetch(USER_AGENT, url)
                    and not parser.crawl_delay(USER_AGENT) and not parser.request_rate(USER_AGENT))

    def verify(self, person: Person, candidates: list[Candidate], hits: list[SearchHit]) -> list[str]:
        from bs4 import BeautifulSoup
        from finder.identity_matcher import contains_name, has_fan_signal

        if not candidates:
            return []
        notes = []
        seen = set()
        attempted = 0
        by_url = {candidate.url: candidate for candidate in candidates}
        for hit in hits:
            if attempted >= self.page_budget:
                break
            if (hit.url in seen or not safe_reference_url(hit.url)
                    or not contains_name(hit.title, person.full_name)):
                continue
            seen.add(hit.url)
            attempted += 1
            try:
                if not self._allowed(hit.url):
                    notes.append(f"Reference skipped by robots/access policy: {hit.url}")
                    continue
                status, body = self._read(hit.url)
                if status != 200:
                    notes.append(f"Reference not read (HTTP {status}; redirects are not followed): {hit.url}")
                    continue
                soup = BeautifulSoup(body, "html.parser")
                page_title = " ".join(node.get_text(" ", strip=True) for node in soup.select("title, h1"))
                if not contains_name(page_title, person.full_name):
                    continue
                for anchor in soup.find_all("a", href=True):
                    parsed = normalize_profile_url(urljoin(hit.url, anchor["href"]))
                    if not parsed or parsed[1] not in by_url:
                        continue
                    # Require a local attribution, not an unrelated site-wide social footer.
                    parent = anchor.find_parent(["p", "li", "figcaption"]) or anchor
                    context = parent.get_text(" ", strip=True)
                    if (len(context) > 1800 or not contains_name(context, person.full_name)
                            or has_fan_signal(context)):
                        continue
                    candidate = by_url[parsed[1]]
                    evidence = Evidence("A public reference page directly links this profile beside the person's name.",
                                        hit.url, "strong")
                    if evidence not in candidate.evidence:
                        candidate.evidence.append(evidence)
            except Exception as exc:
                notes.append(f"Reference could not be checked: {hit.url} ({type(exc).__name__}: {str(exc)[:180]})")
        return notes
