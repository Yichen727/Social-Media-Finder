"""Search scheduling, time budget, and platform scope regressions."""

import csv
import io
from threading import Barrier, Event, Lock
from unittest.mock import Mock, patch

import pytest
from streamlit.testing.v1 import AppTest

from finder.export import export_csv, result_rows
from finder.models import Candidate, MatchStatus, Person, Platform, PlatformResult, QueryRun, SearchHit
from finder.service import FinderService


@pytest.mark.parametrize("platform,url", [
    (Platform.X, "https://x.com/alex"),
    (Platform.INSTAGRAM, "https://www.instagram.com/alex/"),
])
def test_social_search_never_parses_or_verifies_career(platform, url):
    engine = Mock(search=lambda query: QueryRun(query, hits=[SearchHit(
        "Alex Morgan", url, "Senior Creative Producer at Example Studios · 2K followers")]))
    verifier = Mock()
    with patch("finder.linkedin_profile.populate_career_details") as career:
        result = FinderService(engine, verifier).search_platform(Person("Alex Morgan", "Producer", "Example Studios"), platform)
    career.assert_not_called()
    verifier.verify.assert_not_called()
    assert result.candidates[0].follower_count == 2000
    assert result.candidates[0].job_title == result.candidates[0].company == ""
    assert not any("Producer" in run.query.text or "Example Studios" in run.query.text for run in result.runs)


def test_independent_discovery_queries_overlap():
    overlapping, lock = Event(), Lock()
    active = 0
    def search(query):
        nonlocal active
        with lock:
            active += 1
            if active >= 2:
                overlapping.set()
        overlapping.wait(timeout=1)
        with lock:
            active -= 1
        return QueryRun(query)
    FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.INSTAGRAM)
    assert overlapping.is_set()


def test_selected_platforms_overlap_and_unselected_platforms_are_not_searched():
    barrier = Barrier(2, timeout=2)
    def search(person, platform):
        barrier.wait()
        return PlatformResult(platform, MatchStatus.NONE)
    service = FinderService(Mock())
    with patch.object(service, "search_platform", side_effect=search) as requests:
        results = list(service.search_selected(Person("Alex Morgan"), [Platform.INSTAGRAM, Platform.X]))
    assert {result.platform for result in results} == {Platform.INSTAGRAM, Platform.X}
    assert requests.call_count == 2


def test_budget_preserves_all_accounts_and_refresh_can_complete_counts():
    clock = [0.0]
    lock = Lock()
    def search(query):
        if query.stage == "Public profile metrics":
            with lock:
                clock[0] += 6
            handle = query.text.split("site:x.com/", 1)[1].split()[0]
            return QueryRun(query, hits=[SearchHit(f"@{handle}", f"https://x.com/{handle}", "2K Followers")])
        return QueryRun(query, hits=[SearchHit("Alex Morgan", f"https://x.com/alex{i}", "") for i in range(8)])
    service = FinderService(Mock(search=search))
    with patch("finder.service.monotonic", side_effect=lambda: clock[0]):
        result = service.search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 8
    assert 0 < sum(c.follower_count is not None for c in result.candidates) < 8
    assert any(error.kind == "budget" for error in result.errors)
    result = service.search_platform(Person("Alex Morgan"), Platform.X)
    assert all(c.follower_count == 2000 for c in result.candidates)
    assert not any(error.kind == "budget" for error in result.errors)


def test_social_only_csv_omits_career_fields_even_for_stale_candidates():
    result = PlatformResult(Platform.X, MatchStatus.POSSIBLE, candidates=[
        Candidate(Platform.X, "https://x.com/alex", "alex", "Alex Morgan", job_title="Producer", company="Studio", follower_count=100)
    ])
    rows = result_rows(Person("Alex Morgan", "Producer", "Studio"), [result])
    assert rows[0]["Profession"] == rows[0]["Company"] == ""
    restored = list(csv.DictReader(io.StringIO(export_csv(rows).decode("utf-8-sig"))))
    assert "Profession" not in restored[0] and "Company" not in restored[0]
    assert restored[0]["Followers"] == "100"


def test_social_only_ui_hides_career_inputs_and_columns():
    from pathlib import Path
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.multiselect[0].set_value(["X / Twitter"]).run()
    assert len(app.text_input) == 1
    app.text_input[0].set_value("Alex Morgan")
    result = PlatformResult(Platform.X, MatchStatus.POSSIBLE, candidates=[
        Candidate(Platform.X, "https://x.com/alex", "alex", "Alex Morgan", follower_count=2000)
    ])
    with patch("finder.service.FinderService.search_platform", return_value=result):
        app.button[0].click().run()
    assert not app.exception
    assert "Profession" not in app.dataframe[0].value.columns
    assert "Company" not in app.dataframe[0].value.columns


def test_missing_counts_do_not_add_extra_buttons_or_incomplete_warnings():
    from pathlib import Path
    from finder.models import Query, SearchError
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.multiselect[0].set_value(["X / Twitter"]).run()
    app.text_input[0].set_value("Alex Morgan")
    result = PlatformResult(Platform.X, MatchStatus.POSSIBLE, candidates=[
        Candidate(Platform.X, "https://x.com/alex", "alex", "Alex Morgan")
    ], runs=[QueryRun(Query("Follower lookup budget", ""), error=SearchError(
        "budget", "Some follower counts were unavailable within the search time budget.", "budget reached"))])
    with patch("finder.service.FinderService.search_platform", return_value=result):
        app.button[0].click().run()
    assert not app.exception
    assert not any(button.label == "Fill missing Followers" for button in app.button)
    assert not any("incomplete" in warning.value.lower() for warning in app.warning)
    app.radio[0].set_value("Profiles").run()
    assert not app.exception
    assert not any("incomplete" in warning.value.lower() for warning in app.warning)
    assert not any("unavailable within" in caption.value for caption in app.caption)


def test_complete_social_provider_failure_gets_one_recovery_attempt():
    def search(query):
        if query.stage != "Discovery retry":
            raise TimeoutError("temporary provider failure")
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "2K Followers")])
    result = FinderService(Mock(search=search)).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 1 and result.candidates[0].follower_count == 2000
    assert sum(run.query.stage == "Discovery retry" for run in result.runs) == 1
    assert result.partial


def test_x_discovery_and_metric_lookups_never_query_the_legacy_index():
    def search(query):
        if query.stage == "Public profile metrics":
            return QueryRun(query)
        return QueryRun(query, hits=[SearchHit("Alex Morgan", "https://x.com/alex", "")])
    engine = Mock(search=Mock(side_effect=search))
    result = FinderService(engine).search_platform(Person("Alex Morgan"), Platform.X)
    assert len(result.candidates) == 1
    assert sum(run.query.stage == "Public profile metrics" for run in result.runs) == 2
    assert all("twitter.com" not in call.args[0].text for call in engine.search.call_args_list)
