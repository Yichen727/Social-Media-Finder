import pytest

from finder.models import Person, Platform
from finder.query_builder import build_queries, manual_search_url


@pytest.mark.parametrize("name", ["", "   ", "12345", "---"])
def test_name_is_required(name):
    with pytest.raises(ValueError, match="full name"):
        Person(name)


def test_names_are_cleaned_and_optional_fields_default_empty():
    person = Person("  Emma   Watson  ")
    assert person.full_name == "Emma Watson"
    assert (person.profession, person.organization, person.country) == ("", "", "")


def test_overlong_fields_are_rejected():
    with pytest.raises(ValueError, match="160"):
        Person("Alex Morgan", country="x" * 161)


@pytest.mark.parametrize("platform", list(Platform))
def test_queries_stay_broad_before_adding_context(platform):
    queries = build_queries(Person("Alex Morgan", "Scientist", "Example Lab", "British"), platform)
    assert len(queries) == {Platform.LINKEDIN: 4, Platform.INSTAGRAM: 2, Platform.X: 2}[platform]
    assert '"Alex Morgan"' in queries[0].text
    assert "Example Lab" not in queries[0].text
    if platform == Platform.LINKEDIN:
        assert "Scientist" in queries[1].text
        assert "Example Lab" not in queries[1].text
        assert "Example Lab" in queries[2].text
        assert "Scientist" not in queries[2].text
        assert queries[-1].stage == "Public reference search"
    else:
        assert all("Example Lab" not in query.text and "Scientist" not in query.text for query in queries)
        assert all(query.stage != "Public reference search" for query in queries)
    assert "British" not in queries[1].text


@pytest.mark.parametrize("field,value", [("profession", "Director"), ("country", "Chinese")])
def test_social_search_ignores_optional_career_and_country_context(field, value):
    queries = build_queries(Person("Alex Morgan", **{field: value}), Platform.INSTAGRAM)
    assert all(value not in query.text for query in queries)


def test_x_domain_and_encoded_manual_search():
    queries = build_queries(Person("Alex Morgan"), Platform.X)
    assert "site:x.com" in queries[0].text
    assert any(query.stage == "Follower discovery" for query in queries)
    assert all("twitter.com" not in query.text for query in queries)
    assert manual_search_url('"Alex Morgan"') == "https://duckduckgo.com/?q=%22Alex+Morgan%22"


def test_user_text_cannot_insert_search_operators():
    queries = build_queries(Person('Alex " OR site:example.com'), Platform.LINKEDIN)
    assert '"Alex OR site example com"' in queries[0].text
