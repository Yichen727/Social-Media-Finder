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
    assert len(queries) == (4 if platform == Platform.LINKEDIN else 3)
    assert '"Alex Morgan"' in queries[0].text
    assert "Example Lab" not in queries[0].text
    if platform == Platform.LINKEDIN:
        assert "Scientist" in queries[1].text
        assert "Example Lab" not in queries[1].text
        assert "Example Lab" in queries[2].text
        assert "Scientist" not in queries[2].text
    else:
        assert "Example Lab" in queries[1].text
        assert "Scientist" not in queries[1].text
    assert "British" not in queries[1].text
    assert queries[-1].stage == "Public reference search"


@pytest.mark.parametrize("field,value", [("profession", "Director"), ("country", "Chinese")])
def test_other_optional_context_is_used(field, value):
    queries = build_queries(Person("Alex Morgan", **{field: value}), Platform.INSTAGRAM)
    assert value in queries[1].text


def test_legacy_x_domain_and_encoded_manual_search():
    queries = build_queries(Person("Alex Morgan"), Platform.X)
    assert "site:x.com/" in queries[0].text
    assert "site:twitter.com/" in queries[1].text
    assert manual_search_url('"Alex Morgan"') == "https://duckduckgo.com/?q=%22Alex+Morgan%22"


def test_user_text_cannot_insert_search_operators():
    queries = build_queries(Person('Alex " OR site:example.com'), Platform.LINKEDIN)
    assert '"Alex OR site example com"' in queries[0].text
