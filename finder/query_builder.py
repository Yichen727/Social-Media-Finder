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
        Platform.INSTAGRAM: "site:instagram.com",
        Platform.X: "site:x.com",
    }[platform]
    queries = [Query("Broad search", f"{scope} {name}")]
    if platform == Platform.LINKEDIN:
        # Search job title and company independently; neither may hide the other.
        contexts = list(dict.fromkeys(
            search_term(value) for value in (person.profession, person.organization) if value
        ))
        for context in contexts:
            queries.append(Query("Contextual search", f"{scope} {name} {context}"))
        if not contexts:
            queries.append(Query("Contextual search", f"{scope} {name} official"))
    else:
        # Career context belongs to LinkedIn only. Social searches focus on names/metrics.
        queries.append(Query("Follower discovery", f'{scope} {name} "Followers"'))
        return queries
    exclusions = "-site:linkedin.com -site:instagram.com -site:x.com -site:twitter.com"
    queries.append(Query("Public reference search", f'{name} "linkedin.com/in/" {exclusions}'))
    return queries


def manual_search_url(query: str) -> str:
    return "https://duckduckgo.com/?" + urlencode({"q": query})
