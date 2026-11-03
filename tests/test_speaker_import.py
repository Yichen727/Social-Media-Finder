import csv
import io
from unittest.mock import patch

import pytest

from finder.speaker_import import SpeakerImportError, TranscriptIndex, load_speaker_csv, normalize_reference


def csv_bytes(headers, rows, *, delimiter=",", encoding="utf-8-sig"):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode(encoding)


def test_import_distinguishes_scope_existing_values_and_pending_rows():
    data = csv_bytes(["Ref Number", "High-res video name", "YouTube Caption", "Speakers", "ID"], [
        ["01", "A talk", "No description", "Existing Person, Director", "0007"],
        [" 2 ", "Another talk", "Caption", "", "0008"],
        ["", "Unnumbered", "", "", "0009"],
        ["YES", "Invalid reference", "", "Do not touch", "0010"],
        ["94", "Out of scope", "", "", "0011"],
    ])
    table = load_speaker_csv(data)
    assert len(table.rows) == 5
    assert [row.reference for row in table.eligible_rows] == [1, 2]
    assert [row.row_id for row in table.pending_rows] == [1]
    assert [row.issue for row in table.rows] == [None, None, "missing_reference", "invalid_reference", "out_of_scope"]
    assert table.rows[0].values["Ref Number"] == "01"
    assert table.rows[1].values["Ref Number"] == " 2 "
    assert table.rows[0].values["Speakers"] == "Existing Person, Director"
    assert table.rows[0].values["ID"] == "0007"


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_delimiters_round_trip_quoted_multiline_source_cells(delimiter):
    headers = ["Ref Number", "High-res video name", "YouTube Caption", "Speakers", "Match status"]
    rows = [["5", 'A title, with "quotes"', "line one\r\nline two; with | and tabs\t", "", "Keep this"]]
    table = load_speaker_csv(csv_bytes(headers, rows, delimiter=delimiter))
    assert table.delimiter == delimiter
    assert table.to_csv_bytes().startswith(b"\xef\xbb\xbf")
    restored = list(csv.reader(io.StringIO(table.to_csv_bytes().decode("utf-8-sig"), newline=""), delimiter=delimiter))
    assert restored == [headers, *rows]


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "cp1252"])
def test_supported_encodings_preserve_accents(encoding):
    data = csv_bytes(["Ref Number", "Speakers", "Title"], [["5", "", "András Szántó — Rabaté"]], encoding=encoding)
    table = load_speaker_csv(data)
    assert table.encoding == encoding
    assert table.rows[0].values["Title"] == "András Szántó — Rabaté"


def test_explicit_encoding_and_delimiter_are_respected():
    data = csv_bytes(["Ref Number", "Speakers", "Title"], [["1", "", "张伟"]], encoding="gb18030", delimiter=";")
    table = load_speaker_csv(data, encoding="gb18030", delimiter=";")
    assert table.rows[0].values["Title"] == "张伟"
    with pytest.raises(SpeakerImportError, match="decoded"):
        load_speaker_csv(data, encoding="utf-8", delimiter=";")


def test_header_lookup_preserves_original_names_and_adds_only_missing_speakers():
    table = load_speaker_csv(csv_bytes([" REF   NUMBER ", " high-RES VIDEO name ", "YouTube CAPTION"], [["3", "Title", "Caption"]]))
    assert table.reference_column == " REF   NUMBER "
    assert table.video_name_column == " high-RES VIDEO name "
    assert table.caption_column == "YouTube CAPTION"
    assert table.headers == (" REF   NUMBER ", " high-RES VIDEO name ", "YouTube CAPTION", "Speakers")
    assert table.rows[0].cells == ("3", "Title", "Caption", "")


def test_existing_singular_speaker_column_is_reused():
    table = load_speaker_csv(csv_bytes(["Ref Number", "Speaker"], [["1", "Existing Person"]]))
    assert table.headers == ("Ref Number", "Speaker")
    assert table.speaker_column == "Speaker"
    assert not table.pending_rows


def test_two_speaker_columns_require_a_choice_without_losing_either():
    data = csv_bytes(["Ref Number", "Speaker", "Speakers"], [["1", "One", ""]])
    with pytest.raises(SpeakerImportError, match="Choose speaker_column"):
        load_speaker_csv(data)
    table = load_speaker_csv(data, speaker_column="speakers")
    assert table.rows[0].values["Speaker"] == "One"
    assert table.rows[0].needs_speaker
    with pytest.raises(SpeakerImportError, match="Select an existing"):
        load_speaker_csv(data, speaker_column="Ref Number")


def test_duplicate_references_remain_separate_and_are_not_silently_processed():
    table = load_speaker_csv(csv_bytes(["Ref Number", "Speakers"], [["1", ""], ["01", "Existing"], ["10", ""]]))
    assert [row.row_id for row in table.rows] == [0, 1, 2]
    assert [row.issue for row in table.rows] == ["duplicate_reference", "duplicate_reference", None]
    assert [row.reference for row in table.pending_rows] == [10]
    assert table.rows[1].values["Speakers"] == "Existing"


@pytest.mark.parametrize("value,expected", [("05", 5), (" 93 ", 93), ("0", None), ("1.0", None), ("YES", None), ("1e1", None), ("-1", None), ("", None)])
def test_reference_normalization_does_not_guess(value, expected):
    assert normalize_reference(value) == expected


@pytest.mark.parametrize("data", [
    b"Other,Speakers\r\n1,\r\n",
    b"Ref Number,ref number\r\n1,2\r\n",
    b"Ref Number,\r\n1,\r\n",
    b"Ref Number,Speakers\r\n1,Name,Extra\r\n",
    b"Ref Number,Speakers\r\n1\r\n",
    b'Ref Number,Speakers\r\n1,"unclosed\r\n',
    b"",
])
def test_invalid_csv_is_rejected_without_dropping_or_shifting_values(data):
    with pytest.raises(SpeakerImportError):
        load_speaker_csv(data)


def test_source_values_cannot_be_changed_through_preview_dicts():
    table = load_speaker_csv(b"Ref Number,Speakers\r\n1,Original\r\n")
    preview = table.rows[0].values
    preview["Speakers"] = "Edited preview"
    assert table.rows[0].values["Speakers"] == "Original"


def test_optional_sources_can_be_missing_and_blank_rows_are_preserved():
    table = load_speaker_csv(b"Ref Number,Speakers\r\n1,\r\n,\r\n\r\n")
    assert table.video_name_column is None and table.caption_column is None
    assert len(table.rows) == 2
    assert len(table.pending_rows) == 1


def make_docx(folder, relative):
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"Contents must not be read by the filename index.")
    return path.resolve()


def test_transcript_index_is_lazy_and_never_opens_documents(tmp_path):
    expected = make_docx(tmp_path, "05. Talk.docx")
    index = TranscriptIndex(tmp_path)
    assert not index.loaded
    with patch("finder.speaker_import.os.walk", wraps=__import__("os").walk) as walk:
        with patch("pathlib.Path.open", side_effect=AssertionError("DOCX opened")):
            assert index.lookup("5").path == expected
            assert index.lookup("05").path == expected
            assert index.lookup(6).status == "missing"
    assert walk.call_count == 1


def test_exact_matching_case_insensitive_extensions_and_generic_parent_layout(tmp_path):
    one = make_docx(tmp_path, "01. Talk.DOCX")
    ten = make_docx(tmp_path, "10. Other.docx")
    nested = make_docx(tmp_path, "27. Panel/transcript.docx")
    make_docx(tmp_path, "~$01. Talk.docx")
    make_docx(tmp_path, "__MACOSX/._01. Talk.docx")
    index = TranscriptIndex(tmp_path)
    assert index.lookup(1).path == one
    assert index.lookup(10).path == ten
    assert index.lookup(27).path == nested
    assert index.lookup(2).status == "missing"


def test_numbered_root_folder_can_identify_generic_transcript(tmp_path):
    folder = tmp_path / "27"
    expected = make_docx(folder, "transcript.docx")
    assert TranscriptIndex(folder).lookup(27).path == expected


def test_duplicate_and_conflicting_transcripts_are_not_selected(tmp_path):
    make_docx(tmp_path, "a/05. Talk.docx")
    make_docx(tmp_path, "b/5. Other.docx")
    make_docx(tmp_path, "27/06. Wrong folder.docx")
    index = TranscriptIndex(tmp_path)
    duplicate = index.lookup(5)
    assert duplicate.status == "duplicate" and duplicate.path is None and len(duplicate.paths) == 2
    assert index.lookup(6).status == "conflicting_reference"
    assert index.lookup(27).status == "conflicting_reference"


def test_invalid_lookup_does_not_scan_and_missing_folder_is_reported(tmp_path):
    index = TranscriptIndex(tmp_path / "does-not-exist")
    assert index.lookup("YES").status == "invalid_reference"
    assert not index.loaded
    assert index.lookup(1).status == "folder_error"
    assert TranscriptIndex("").lookup(1).status == "folder_error"


def test_refresh_invalidates_metadata_without_scanning_immediately(tmp_path):
    first = make_docx(tmp_path, "01. First.docx")
    index = TranscriptIndex(tmp_path)
    assert index.lookup(1).path == first
    make_docx(tmp_path, "nested/1. Another.docx")
    assert index.lookup(1).path == first
    index.refresh()
    assert not index.loaded
    assert index.lookup(1).status == "duplicate"
