import csv
import io
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from streamlit.testing.v1 import AppTest

from finder.speaker_extract import SpeakerExtractor
from finder.models import MatchStatus, PlatformResult

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class UploadedCSV(io.BytesIO):
    name = "talks.csv"


def upload(rows=None, *, headers=None, encoding="utf-8-sig", name="talks.csv"):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers or ["Ref Number", "High-res video name", "YouTube Caption", "Speakers", "ID"])
    writer.writerows(rows or [["1", "Old talk", "No description", "Existing Person", "0001"],
                             ["5", "Keynote by András Szántó.mp4", "No description", "", "0005"],
                             ["18", "Louvre Abu Dhabi case study", "No description", "", "0018"],
                             ["YES", "Extra row", "", "Do not change", "0000"]])
    uploaded = UploadedCSV(output.getvalue().encode(encoding))
    uploaded.name = name
    return uploaded


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def speakers(app):
    return next(widget for widget in app.radio if widget.label == "Workspace").set_value("Speakers")


def edit(app, row, value):
    state = app.session_state["speaker_workspace"]
    key = state["editor_key"]
    previous = dict(app.session_state[key])
    changes = dict(previous.get("edited_rows", {}))
    changes[row] = {"Speakers": value}
    app.session_state[key] = {"edited_rows": changes, "added_rows": [], "deleted_rows": []}


def test_workspace_has_no_network_calls_and_waits_for_a_csv():
    with patch("finder.service.FinderService.search_selected", side_effect=AssertionError("No search")):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
    assert not app.exception
    assert not app.dataframe
    assert len(app.get("file_uploader")) == 1
    assert any("Upload a CSV" in info.value for info in app.info)


def test_upload_preview_find_edit_approve_and_export_without_network():
    data = upload()
    with patch("finder.speaker_workspace.st.file_uploader", return_value=data), \
            patch("finder.service.FinderService.search_selected", side_effect=AssertionError("No search")):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        assert not app.exception
        assert len(app.dataframe[0].value) == 3
        assert app.get("download_button")[0].proto.disabled
        button(app, "Find speakers").click().run()
        assert not app.exception
        review = app.session_state["speaker_workspace"]["review"]
        assert review.values() == {0: "Existing Person", 1: "András Szántó", 2: ""}
        edit(app, 2, "Manuel Rabaté")
        app.run()
        assert not app.exception
        button(app, "Apply reviewed changes").click().run()
        assert not app.exception
        assert not app.get("download_button")[0].proto.disabled
        output = review.export_csv()
        restored = list(csv.reader(io.StringIO(output.decode("utf-8-sig"))))
        assert [row[3] for row in restored[1:]] == ["Existing Person", "András Szántó", "Manuel Rabaté", "Do not change"]
        assert [row[4] for row in restored[1:]] == ["0001", "0005", "0018", "0000"]
        edit(app, 1, "")
        app.run()
        assert not app.exception and app.get("download_button")[0].proto.disabled


def test_pending_edit_survives_find_and_repeated_edits_do_not_disappear():
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload()):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        button(app, "Find speakers").click().run()
        edit(app, 1, "")
        button(app, "Find speakers").click().run()
        assert not app.exception
        review = app.session_state["speaker_workspace"]["review"]
        assert review.values()[1] == ""
        edit(app, 2, "First Edit")
        app.run()
        edit(app, 2, "Second Edit")
        app.run()
        assert not app.exception and review.values()[2] == "Second Edit"
        button(app, "Reset review").click().run()
        assert review.values()[1] == "András Szántó" and review.values()[2] == ""
        assert not review.ready


def test_evidence_and_rerenders_do_not_rerun_extraction_or_read_docx(tmp_path):
    path = tmp_path / "18. Case study.docx"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>[00:00:00] Speaker 1: My name is Manuel Rabaté. I am presenting a case study.</w:t></w:r></w:p></w:body></w:document>')
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload()):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        next(widget for widget in app.text_input if widget.label == "Transcript folder").set_value(str(tmp_path))
        button(app, "Find speakers").click().run()
        review = app.session_state["speaker_workspace"]["review"]
        assert review.values()[2] == "Manuel Rabaté"
        with patch.object(SpeakerExtractor, "extract_all", side_effect=AssertionError("Do not repeat")), \
                patch.object(SpeakerExtractor, "read_opening", side_effect=AssertionError("Do not reread")):
            next(widget for widget in app.selectbox if widget.label == "Talk").set_value(2).run()
            assert any("Manuel Rabaté" in widget.value for widget in app.text)
            edit(app, 2, "Reviewed Person")
            app.run()
            button(app, "Apply reviewed changes").click().run()
            assert not app.exception


def test_switching_workspaces_preserves_review_and_manual_edits():
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload()):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        button(app, "Find speakers").click().run()
        edit(app, 2, "Reviewed Person")
        app.run()
        next(widget for widget in app.radio if widget.label == "Workspace").set_value("Social search").run()
    # Streamlit cannot rehydrate file_uploader; the loaded bytes live separately.
    speakers(app).run()
    assert not app.exception
    assert app.session_state["speaker_workspace"]["review"].values()[2] == "Reviewed Person"
    assert app.dataframe[0].value.iloc[2]["Speakers"] == "Reviewed Person"


def test_changed_file_starts_a_separate_review():
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload()) as uploaded:
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        edit(app, 2, "Reviewed Person")
        app.run()
        uploaded.return_value = upload([["12", "Artist Talk_ Farah Al Qassimi.mp4", "No description", "", "0012"]], name="other.csv")
        app.run()
        assert not app.exception
        review = app.session_state["speaker_workspace"]["review"]
        assert review.values() == {0: ""} and not review.ready
        assert app.session_state["speaker_workspace"]["filename"] == "other.csv"


def test_bad_csv_and_dual_speaker_columns_have_recoverable_controls():
    data = upload([["5", "Title", "First value", "Second value"]],
                  headers=["Ref Number", "High-res video name", "Speaker", "Speakers"])
    with patch("finder.speaker_workspace.st.file_uploader", return_value=data):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        assert not app.exception and any("Both Speaker and Speakers" in message.value for message in app.error)
        next(widget for widget in app.selectbox if widget.label == "Speaker column").set_value("Speaker").run()
        assert not app.exception and not app.error
        assert app.session_state["speaker_workspace"]["review"].table.speaker_column == "Speaker"


def test_encoding_preview_and_override_are_available():
    data = upload(encoding="cp1252")
    with patch("finder.speaker_workspace.st.file_uploader", return_value=data):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        assert app.session_state["speaker_workspace"]["review"].table.encoding == "cp1252"
        next(widget for widget in app.selectbox if widget.label == "Encoding").set_value("UTF-8").run()
        assert not app.exception and any("could not be decoded" in message.value for message in app.error)
        assert not app.get("download_button")
        next(widget for widget in app.selectbox if widget.label == "Encoding").set_value("Windows-1252").run()
        assert not app.exception and not app.error


def test_invalid_folder_does_not_discard_review_edits_or_start_network():
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload()), \
            patch("finder.service.FinderService.search_selected", side_effect=AssertionError("No search")):
        app = AppTest.from_file(APP).run()
        speakers(app).run()
        edit(app, 2, "Reviewed Person")
        next(widget for widget in app.text_input if widget.label == "Transcript folder").set_value("Z:/not-a-real-folder-smf")
        button(app, "Find speakers").click().run()
        assert not app.exception
        assert any("not accessible" in widget.value for widget in app.error)
        assert app.session_state["speaker_workspace"]["review"].values()[2] == "Reviewed Person"


def test_switching_workspaces_preserves_social_form_and_does_not_submit_it():
    with patch("finder.service.FinderService.search_platform",
               side_effect=lambda person, platform: PlatformResult(platform, MatchStatus.NONE)) as search:
        app = AppTest.from_file(APP).run()
        app.multiselect[0].set_value(["LinkedIn"]).run()
        app.text_input[0].set_value("Alex Morgan")
        app.text_input[1].set_value("Producer")
        app.text_input[2].set_value("Example Studios")
        button(app, "Search").click().run()
        assert search.call_count == 1
        speakers(app).run()
        next(widget for widget in app.radio if widget.label == "Workspace").set_value("Social search").run()
        assert not app.exception
        assert app.multiselect[0].value == ["LinkedIn"]
        assert [widget.value for widget in app.text_input] == ["Alex Morgan", "Producer", "Example Studios"]
        assert search.call_count == 1
