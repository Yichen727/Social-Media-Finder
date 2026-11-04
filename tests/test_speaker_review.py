import csv
import io
from dataclasses import replace

import pytest

from finder.speaker_extract import SpeakerExtractor
from finder.speaker_import import load_speaker_csv
from finder.speaker_review import SpeakerReview


def source_table(*, delimiter=",", speaker_header="Speakers"):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    headers = ["Ref Number", "High-res video name", "YouTube Caption", speaker_header, "ID", "Match status"]
    cells = [["1", "Keynote by Existing Person.mp4", "No description", "Original Person, Director", "0001", "Retain"],
             ["05", "Keynote by András Szántó.mp4", 'A caption, with "quotes"\nand a newline', "", "0005", ""],
             ["18", "A case study by Louvre Abu Dhabi", "No description", "", "0018", "Source status"],
             ["", "Keynote by Wrong Person", "", "Unnumbered value", "0000", "Keep"],
             ["YES", "Invalid", "", "", "0010", "Keep"]]
    writer.writerow(headers)
    writer.writerows(cells)
    return load_speaker_csv(output.getvalue().encode("utf-8-sig")), headers, cells


def reviewed():
    table, _, _ = source_table()
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    return review


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_export_requires_approval_and_changes_only_reviewed_speaker_cells(delimiter):
    table, headers, cells = source_table(delimiter=delimiter)
    before = table.to_csv_bytes()
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    with pytest.raises(ValueError, match="Apply reviewed"):
        review.export_csv()
    review.edit({2: 'Manuel Rabaté, "Director"\nPresenter'})
    review.approve()
    exported = review.export_csv()
    restored = list(csv.reader(io.StringIO(exported.decode("utf-8-sig"), newline=""), delimiter=delimiter))
    assert exported.startswith(b"\xef\xbb\xbf")
    assert restored[0] == headers
    expected = [list(row) for row in cells]
    expected[1][3] = "András Szántó"
    expected[2][3] = 'Manuel Rabaté, "Director"\nPresenter'
    assert restored[1:] == expected
    assert table.to_csv_bytes() == before


def test_manual_edits_and_cleared_suggestions_survive_repeated_extraction():
    review = reviewed()
    review.edit({1: "", 2: "Reviewed Person"})
    review.offer(SpeakerExtractor().extract_all(review.table))
    assert review.values()[1] == ""
    assert review.values()[2] == "Reviewed Person"
    assert review.values()[0] == "Original Person, Director"


def test_manual_change_requires_new_approval_but_reverting_restores_it():
    review = reviewed()
    review.approve()
    assert review.ready
    review.edit({1: "A Different Person"})
    assert not review.ready
    with pytest.raises(ValueError):
        review.export_csv()
    review.edit({1: "András Szántó"})
    assert review.ready


def test_new_machine_proposal_requires_review_and_keeps_manual_override():
    review = reviewed()
    review.approve()
    proposal = review.proposals[1]
    changed = replace(proposal, attempts=(replace(proposal.detection, name="Another Person"),))
    review.offer([changed])
    assert not review.ready and review.values()[1] == "Another Person"
    review.edit({1: "Reviewed Person"})
    review.approve()
    review.offer([proposal])
    assert review.ready and review.values()[1] == "Reviewed Person"


def test_reset_explicitly_restores_originals_and_latest_suggestions():
    review = reviewed()
    review.edit({0: "Changed Existing", 1: "", 2: "Manual Person"})
    review.approve()
    review.reset()
    assert not review.ready
    assert review.values() == {0: "Original Person, Director", 1: "András Szántó", 2: ""}


def test_existing_values_can_only_change_through_an_explicit_edit():
    review = reviewed()
    review.approve()
    assert review.values()[0] == "Original Person, Director"
    review.edit({0: ""})
    review.offer(SpeakerExtractor().extract_all(review.table))
    review.approve()
    restored = list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))
    assert restored[1][3] == ""


@pytest.mark.parametrize("edits", [{3: "Out of scope"}, {4: "Invalid reference"}, {200: "Unknown row"}, {1: None}])
def test_invalid_edit_is_rejected_atomically(edits):
    review = reviewed()
    before = review.values()
    with pytest.raises(ValueError):
        review.edit({2: "Must not be partially applied", **edits})
    assert review.values() == before


def test_editing_display_order_cannot_shift_names_to_another_talk():
    review = reviewed()
    rows = list(reversed(review.editor_rows()))
    rows[0]["Speakers"] = "Reviewed Person"
    review.edit({row["_row_id"]: row["Speakers"] for row in rows})
    assert review.values()[2] == "Reviewed Person"
    assert review.values()[1] == "András Szántó"
    assert [row["Ref Number"] for row in review.editor_rows()] == ["1", "05", "18"]


def test_singular_speaker_header_and_source_business_columns_are_preserved():
    table, headers, _ = source_table(speaker_header="Speaker")
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    review.approve()
    restored = list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))
    assert restored[0] == headers
    assert "Speakers" not in restored[0]
    assert restored[3][-1] == "Source status"


def test_wrong_source_proposals_are_rejected_before_replacing_current_ones():
    review = reviewed()
    before = dict(review.proposals)
    for invalid in (replace(review.proposals[1], original_value="Wrong original"),
                    replace(review.proposals[1], reference=99),
                    replace(review.proposals[1], row_id=99)):
        with pytest.raises(ValueError):
            review.offer([invalid])
        assert review.proposals == before
