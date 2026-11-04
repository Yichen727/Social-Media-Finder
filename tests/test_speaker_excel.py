"""Excel import/export regressions: row identity, source preservation, and approval."""
import csv
from datetime import datetime
import io
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
import pytest
from streamlit.testing.v1 import AppTest

from finder.speaker_excel import SpeakerXLSX, load_speaker_xlsx, xlsx_sheet_names
from finder.speaker_extract import SpeakerExtractor
from finder.speaker_import import SpeakerImportError, load_speaker_csv
from finder.speaker_review import SpeakerReview


def workbook_bytes(*, speakers=True):
    book = Workbook()
    sheet = book.active
    sheet.title = "Talks"
    headers = ["Ref Number", "High-res video name", "YouTube Caption", "Speakers", "ID", "Formula", "Date"]
    rows = [
        [1, "Old title", "No description", "Existing Person", "0001", "=1+2", datetime(2026, 11, 4)],
        [5.0, "Keynote by Jane Smith", "No description", None, 5, "=2+3", None],
        [None] * 7,
        ["YES", "Keynote by Wrong Person", "", "Keep this", "0000", "=3+4", None],
        [18, "Generic topic", "No description", "", "0018", "=4+5", None],
    ]
    if not speakers:
        headers.pop(3)
        for row in rows:
            row.pop(3)
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    sheet.cell(3, 5 if speakers else 4).number_format = "0000"
    sheet["D3"].font = Font(bold=True, color="FF0000")
    sheet["D3"].fill = PatternFill("solid", fgColor="FFFF00")
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions
    notes = book.create_sheet("Other sheet")
    notes.append(["Ref Number", "High-res video name", "Speakers"])
    notes.append([2, "Keynote by John Doe", "Untouched Person"])
    notes["E2"] = "=SUM(1,2)"
    notes["F2"].hyperlink = "https://example.com/"
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def review_xlsx(data=None):
    table = load_speaker_xlsx(data or workbook_bytes(), worksheet="Talks")
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    return review


def test_xlsx_import_preserves_row_identity_blank_rows_and_numeric_references():
    table = load_speaker_xlsx(workbook_bytes())
    assert isinstance(table, SpeakerXLSX)
    assert table.worksheet_name == "Talks"
    assert len(table.rows) == 5
    assert [row.row_id for row in table.eligible_rows] == [0, 1, 4]
    assert [row.reference for row in table.eligible_rows] == [1, 5, 18]
    assert table.rows[1].values["ID"] == "0005"
    assert table.rows[2].reference is None
    assert table.rows[0].has_speaker


def test_visible_worksheet_selection():
    data = workbook_bytes()
    assert xlsx_sheet_names(data) == ("Talks", "Other sheet")
    table = load_speaker_xlsx(data, worksheet="Other sheet")
    assert table.rows[0].reference == 2
    assert table.rows[0].values["Speakers"] == "Untouched Person"
    with pytest.raises(SpeakerImportError, match="Choose a visible worksheet"):
        load_speaker_xlsx(data, worksheet="Missing")


def test_both_exports_require_current_approval():
    review = review_xlsx()
    for export in (review.export_csv, review.export_xlsx):
        with pytest.raises(ValueError, match="Apply reviewed"):
            export()
    review.approve()
    assert review.export_xlsx().startswith(b"PK")
    assert review.export_csv().startswith(b"\xef\xbb\xbf")
    review.edit({1: "Edited Person"})
    assert not review.ready
    with pytest.raises(ValueError, match="Apply reviewed"):
        review.export_xlsx()


def test_only_reviewed_speakers_change_and_original_workbook_parts_are_preserved():
    data = workbook_bytes()
    review = review_xlsx(data)
    review.edit({4: "Reviewed Person"})
    review.approve()
    result = review.export_xlsx()
    with ZipFile(io.BytesIO(data)) as original, ZipFile(io.BytesIO(result)) as exported:
        assert original.namelist() == exported.namelist()
        for name in original.namelist():
            if name not in {review.table.worksheet_path, "xl/workbook.xml"}:
                assert original.read(name) == exported.read(name), name
    book = load_workbook(io.BytesIO(result))
    sheet = book["Talks"]
    assert [sheet[f"D{row}"].value for row in (2, 3, 5, 6)] == ["Existing Person", "Jane Smith", "Keep this", "Reviewed Person"]
    assert sheet["D4"].value is None
    assert sheet["D3"].font.bold and sheet["D3"].fill.fgColor.rgb == "00FFFF00"
    assert sheet["F2"].value == "=1+2"
    assert sheet["G2"].value == datetime(2026, 11, 4)
    assert book["Other sheet"]["C2"].value == "Untouched Person"
    assert sheet.freeze_panes == "B2"
    book.close()
    assert review.table.workbook_bytes == data


def test_new_speaker_column_is_appended_without_shifting_original_cells():
    review = review_xlsx(workbook_bytes(speakers=False))
    review.approve()
    book = load_workbook(io.BytesIO(review.export_xlsx()))
    sheet = book["Talks"]
    assert sheet["G1"].value == "Speakers"
    assert sheet["G3"].value == "Jane Smith"
    assert sheet["D3"].value == 5
    assert sheet["D3"].number_format == "0000"
    book.close()


def test_xlsx_to_csv_contains_selected_sheet_only_with_all_rows():
    review = review_xlsx()
    review.approve()
    rows = list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))
    assert len(rows) == 6
    assert rows[2][3] == "Jane Smith" and rows[2][4] == "0005"
    assert rows[3] == [""] * 7
    assert rows[1][5] == "=1+2"
    assert "Untouched Person" not in repr(rows)


def test_csv_to_xlsx_preserves_literal_text_leading_zeroes_and_noneligible_rows():
    table = load_speaker_csv(b'Ref Number,High-res video name,Speakers,ID,Value\n5,Keynote by Jane Smith,,0005,=1+2\nYES,Ignore,Keep,0000,other\n')
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    review.approve()
    book = load_workbook(io.BytesIO(review.export_xlsx()))
    sheet = book.active
    assert sheet["C2"].value == "Jane Smith"
    assert sheet["D2"].value == "0005" and sheet["D2"].data_type == "s"
    assert sheet["E2"].value == "=1+2" and sheet["E2"].data_type == "s"
    assert sheet["C3"].value == "Keep"
    book.close()


def test_edits_are_literal_strings_not_excel_formulas():
    review = review_xlsx()
    review.edit({1: '=HYPERLINK("https://example.com", "Name")'})
    review.approve()
    book = load_workbook(io.BytesIO(review.export_xlsx()))
    assert book["Talks"]["D3"].data_type == "s"
    assert book["Talks"]["D3"].value.startswith("=HYPERLINK")
    book.close()


def test_invalid_workbook_and_uncached_source_formula_produce_useful_errors():
    with pytest.raises(SpeakerImportError, match="readable XLSX"):
        load_speaker_xlsx(b"Not an Excel file")
    book = load_workbook(io.BytesIO(workbook_bytes()))
    book["Talks"]["A3"] = "=2+3"
    output = io.BytesIO()
    book.save(output)
    book.close()
    with pytest.raises(SpeakerImportError, match="formula without a saved result"):
        load_speaker_xlsx(output.getvalue())


def test_merged_speakers_are_not_silently_written_to_the_wrong_row():
    book = load_workbook(io.BytesIO(workbook_bytes()))
    book["Talks"].merge_cells("D3:D4")
    output = io.BytesIO()
    book.save(output)
    book.close()
    with pytest.raises(SpeakerImportError, match="merged cells"):
        load_speaker_xlsx(output.getvalue())


def test_workspace_selects_worksheet_and_allows_both_export_formats_without_network():
    upload = io.BytesIO(workbook_bytes())
    upload.name = "talks.xlsx"
    code = "from finder.speaker_workspace import render_speaker_workspace\nrender_speaker_workspace()"
    with patch("finder.speaker_workspace.st.file_uploader", return_value=upload), \
            patch("finder.service.FinderService.search_selected", side_effect=AssertionError("No network")):
        app = AppTest.from_string(code, default_timeout=15).run()
        assert not app.exception
        export = next(widget for widget in app.selectbox if widget.label == "Export format")
        assert export.value == "XLSX"
        next(button for button in app.button if button.label == "Find speakers").click().run()
        next(button for button in app.button if button.label == "Apply reviewed changes").click().run()
        assert not app.exception and not app.get("download_button")[0].proto.disabled
        next(widget for widget in app.selectbox if widget.label == "Export format").set_value("CSV").run()
        assert not app.exception and app.session_state["speaker_workspace"]["review"].ready
        next(widget for widget in app.selectbox if widget.label == "Worksheet").set_value("Other sheet").run()
        assert not app.exception
        review = app.session_state["speaker_workspace"]["review"]
        assert review.table.worksheet_name == "Other sheet" and not review.ready
