from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from finder.models import MatchStatus, Platform, PlatformResult

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_dashboard_starts_in_english_with_optional_fields_empty():
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert app.title[0].value == "Social Media Finder"
    assert len(app.text_input) == 3
    assert not any("Nationality" in widget.label for widget in app.text_input)
    assert all(widget.value == "" for widget in app.text_input)
    assert len([caption for caption in app.caption if caption.value == "Not Searched"]) == 3


def test_blank_name_blocks_search():
    app = AppTest.from_file(APP).run()
    with patch("finder.service.FinderService.search_platform") as search:
        app.button[0].click().run()
        search.assert_not_called()
    assert app.error[0].value == "Enter a full name containing at least one letter."


def test_empty_results_and_refresh_are_rendered_without_network_calls():
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    with patch("finder.service.FinderService.search_platform",
               side_effect=lambda person, platform: PlatformResult(platform, MatchStatus.NONE)) as search:
        app.button[0].click().run()
        assert not app.exception
        assert search.call_count == 3
        assert sum("no matching profiles" in message.value for message in app.info) == 3
        assert "Match Status" not in app.dataframe[0].value.columns
        refresh = next(button for button in app.button if button.label == "Refresh Search")
        refresh.click().run()
        assert not app.exception and search.call_count == 6


def test_failed_search_is_visibly_distinct_from_no_match():
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    with patch("finder.service.FinderService.search_platform",
               side_effect=lambda person, platform: PlatformResult(platform, MatchStatus.FAILED if platform == Platform.X else MatchStatus.NONE)):
        app.button[0].click().run()
    assert not app.exception
    assert sum("search failed" in message.value for message in app.error) == 1
    assert sum("no matching profiles" in message.value for message in app.info) == 2


def test_candidate_links_and_failure_details_are_available():
    from finder.models import Person, Query, QueryRun, SearchError, SearchHit
    from finder.profile_parser import extract_candidates
    from finder.identity_matcher import rank_candidates

    candidates = rank_candidates(extract_candidates([
        SearchHit("Alex Morgan", "https://x.com/alexmorgan", "Alex Morgan, Scientist")
    ], Platform.X), Person("Alex Morgan"))
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    def result(person, platform):
        if platform != Platform.X:
            return PlatformResult(platform, MatchStatus.NONE)
        return PlatformResult(platform, MatchStatus.POSSIBLE, candidates=candidates, runs=[
            QueryRun(Query("Broad search", "query"), hits=[SearchHit("Alex Morgan", candidates[0].url, "")]),
            QueryRun(Query("Contextual search", "other query"), error=SearchError("timeout", "Timed out", "TimeoutError: timeout"))
        ])
    with patch("finder.service.FinderService.search_platform", side_effect=result):
        app.button[0].click().run()
    app.radio[0].set_value("Profiles").run()
    assert not app.exception
    assert any(element.value == "https://x.com/alexmorgan" for element in app.text)
    assert any("TimeoutError: timeout" in element.value for element in app.text)
    assert any("incomplete" in warning.value for warning in app.warning)
    assert any(button.proto.url == "https://x.com/alexmorgan" for button in app.get("link_button"))


def test_linkedin_role_and_company_are_visible_without_restoring_removed_panels():
    from finder.models import Person, SearchHit
    from finder.profile_parser import extract_candidates
    from finder.identity_matcher import rank_candidates

    candidates = rank_candidates(extract_candidates([
        SearchHit("Alex Morgan - Example Studios | LinkedIn",
                  "https://www.linkedin.com/in/alex-morgan-123/",
                  "Senior Creative Producer at Example Studios / Agency Group")
    ], Platform.LINKEDIN), Person("Alex Morgan", "Senior Creative Producer"))
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    def result(person, platform):
        return PlatformResult(platform, MatchStatus.POSSIBLE, candidates=candidates) if platform == Platform.LINKEDIN else PlatformResult(platform, MatchStatus.NONE)
    with patch("finder.service.FinderService.search_platform", side_effect=result):
        app.button[0].click().run()
    assert not app.exception
    assert "Senior Creative Producer" in list(app.dataframe[0].value["Profession"])
    assert "Example Studios" in list(app.dataframe[0].value["Company"])
    assert not app.metric
    assert not any(expander.label == "Why this profile?" for expander in app.expander)


def test_platform_selection_can_search_one_platform_and_refresh_only_that_platform():
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    app.multiselect[0].set_value(["LinkedIn"])
    with patch("finder.service.FinderService.search_platform",
               side_effect=lambda person, platform: PlatformResult(platform, MatchStatus.NONE)) as search:
        app.button[0].click().run()
        assert not app.exception
        assert search.call_count == 1
        assert search.call_args.args[1] == Platform.LINKEDIN
        assert list(app.dataframe[0].value["Platform"]) == ["LinkedIn"]
        next(button for button in app.button if button.label == "Refresh Search").click().run()
        assert search.call_count == 2
        assert all(call.args[1] == Platform.LINKEDIN for call in search.call_args_list)


def test_no_platform_selection_blocks_search():
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    app.multiselect[0].set_value([])
    with patch("finder.service.FinderService.search_platform") as search:
        app.button[0].click().run()
    assert not app.exception
    search.assert_not_called()
    assert app.error[0].value == "Select at least one platform."
    assert not app.dataframe


def test_list_filter_and_numeric_sort_are_shared_by_csv_without_researching():
    from finder.models import Candidate
    from finder.export import export_csv

    def result(person, platform):
        return PlatformResult(platform, MatchStatus.POSSIBLE, candidates=[
            Candidate(platform, f"https://example.com/{platform.name}", "alex", "Alex Morgan",
                      job_title="Producer", company="Example Studios", nationality="British",
                      follower_count=1000 if platform == Platform.LINKEDIN else 20000)
        ])
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    with patch("finder.service.FinderService.search_platform", side_effect=result) as search:
        app.button[0].click().run()
        app.multiselect[1].set_value(["LinkedIn", "Instagram"])
        with patch("finder.export.export_csv", wraps=export_csv) as download:
            app.run()
            rows = download.call_args.args[0]
            assert [row["Platform"] for row in rows] == ["Instagram", "LinkedIn"]
            assert [row["Followers"] for row in rows] == [20000, 1000]
            assert list(app.dataframe[0].value["Followers"]) == [20000, 1000]
            assert len(app.get("download_button")) == 1
            app.selectbox[0].set_value("Followers (lowest first)").run()
            assert [row["Followers"] for row in download.call_args.args[0]] == [1000, 20000]
        assert search.call_count == 3
    assert not app.exception


def test_empty_list_filter_disables_export_and_does_not_crash():
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("Alex Morgan")
    with patch("finder.service.FinderService.search_platform",
               side_effect=lambda person, platform: PlatformResult(platform, MatchStatus.NONE)):
        app.button[0].click().run()
    app.multiselect[1].set_value([]).run()
    assert not app.exception
    assert app.get("download_button")[0].proto.disabled
    assert not app.dataframe
