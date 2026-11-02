from finder.identity_matcher import rank_candidates
from finder.models import Evidence, MatchStatus, Person, Platform, SearchHit
from finder.profile_parser import extract_candidates


def candidate(title="Alex Morgan", handle="alexmorgan", snippet=""):
    return extract_candidates([SearchHit(title, f"https://x.com/{handle}", snippet)], Platform.X)[0]


def test_matching_name_is_possible_never_automatically_official():
    match = rank_candidates([candidate(snippet="The official account of Alex Morgan")], Person("Alex Morgan"))[0]
    assert match.status == MatchStatus.POSSIBLE
    assert match.confidence == "Medium"
    assert any("ownership is unconfirmed" in note for note in match.cautions)


def test_similar_name_does_not_match():
    assert rank_candidates([candidate("Alexa Morgan", "alexamorgan", "Friend of Alex Morgan")], Person("Alex Morgan")) == []


def test_fan_account_is_rejected_even_with_correct_name_and_context():
    assert rank_candidates([candidate(snippet="Official fan account for scientist Alex Morgan")],
                           Person("Alex Morgan", "Scientist")) == []


def test_fan_handle_is_rejected():
    assert rank_candidates([candidate(handle="alexfanpage")], Person("Alex Morgan")) == []


def test_news_and_archive_profiles_are_rejected():
    for title in ("Alex Morgan News", "Alex Morgan Archives", "Alex Morgan Archive", "Alex Morgan Updates", "Alex Morgan fan"):
        assert rank_candidates([candidate(title=title, handle="alexresearch")], Person("Alex Morgan")) == []
    assert rank_candidates([candidate(handle="alexmorganfans")], Person("Alex Morgan")) == []


def test_context_can_order_same_name_candidates():
    matches = rank_candidates([candidate(handle="alex1", snippet="Director at Example Lab"),
                               candidate(handle="alex2", snippet="Scientist at Example Lab")],
                              Person("Alex Morgan", "Scientist", "Example Lab"))
    assert matches[0].handle == "alex2"
    assert matches[0].score > matches[1].score


def test_two_independent_direct_reference_domains_are_required():
    match = candidate()
    match.evidence = [Evidence("Direct link", "https://www.bbc.com/people/alex", "strong"),
                      Evidence("Direct link", "https://www.bbc.co.uk/profile/alex", "strong")]
    assert rank_candidates([match], Person("Alex Morgan"))[0].status == MatchStatus.POSSIBLE
    match.evidence.append(Evidence("Direct link", "https://www.un.org/people/alex", "strong"))
    assert rank_candidates([match], Person("Alex Morgan"))[0].status == MatchStatus.LIKELY


def test_diacritics_and_non_latin_names():
    assert rank_candidates([candidate(title="José García", handle="josegarcia")], Person("Jose Garcia"))
    assert rank_candidates([candidate(title="张伟", handle="zhangwei")], Person("张伟"))


def test_reranking_does_not_duplicate_evidence():
    match = candidate()
    rank_candidates([match], Person("Alex Morgan"))
    count = len(match.evidence)
    rank_candidates([match], Person("Alex Morgan"))
    assert len(match.evidence) == count
