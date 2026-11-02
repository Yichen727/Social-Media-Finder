"""Small query budget: broad, contextual, then independent references."""

import re
from urllib.parse import urlencode

from finder.models import Person, Platform, Query


def search_term(value: str) -> str:
    # Strip search operators from user input rather than interpreting them as queries.
    return " ".join(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", value, flags=re.UNICODE))


def build_queries(person: Person, platform: Platform) -> list[Query]:
    name = f'"{search_term(person.full_name)}"'
    scope = {
        Platform.LINKEDIN: "site:linkedin.com/in/",
        Platform.INSTAGRAM: "site:instagram.com/",
        Platform.X: "site:x.com/",
    }[platform]
    queries = [Query("Broad search", f"{scope} {name}")]
    context = search_term(person.organization or person.profession or person.country)
    # Only one optional condition at a time: broad discovery is never over-constrained.
    if context:
        context_scope = "site:twitter.com/" if platform == Platform.X else scope
        queries.append(Query("Contextual search", f"{context_scope} {name} {context}"))
    elif platform == Platform.X:
        queries.append(Query("Legacy domain search", f"site:twitter.com/ {name}"))
    else:
        queries.append(Query("Contextual search", f"{scope} {name} official"))
    reference = {
        Platform.LINKEDIN: '"linkedin.com/in/"',
        Platform.INSTAGRAM: '"instagram.com/"',
        Platform.X: '("x.com/" OR "twitter.com/")',
    }[platform]
    exclusions = "-site:linkedin.com -site:instagram.com -site:x.com -site:twitter.com"
    queries.append(Query("Public reference search", f"{name} {reference} {exclusions}"))
    return queries


def manual_search_url(query: str) -> str:
    return "https://duckduckgo.com/?" + urlencode({"q": query})
