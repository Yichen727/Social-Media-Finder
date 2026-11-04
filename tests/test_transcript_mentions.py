import csv
import io

import pytest

from finder.speaker_extract import SpeakerExtractor, TranscriptParagraph, extract_transcript
from finder.speaker_import import TranscriptIndex, load_speaker_csv
from finder.speaker_review import SpeakerReview
from tests.test_speaker_extract import docx


def imported(title="Generic session", caption="No description"):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Ref Number", "High-res video name", "YouTube Caption", "Speakers", "ID"])
    writer.writerow(["5", title, caption, "", "0005"])
    writer.writerow(["", "Extra row", "", "Keep existing*", "0000"])
    return load_speaker_csv(output.getvalue().encode("utf-8-sig"))


def test_names_in_narration_and_acknowledgments_need_no_speaker_role():
    paragraphs = (
        TranscriptParagraph(2, "We read books by Jane Smith and John Doe. Thanks Tim for joining us.", "[00:00:20]", 20, "1"),
        TranscriptParagraph(3, "Sarah O’Connor's work helped Jane Smith develop new ideas.", "[00:00:40]", 40, "2"),
    )
    result = extract_transcript(paragraphs)
    assert result.names == ("Jane Smith", "John Doe", "Tim", "Sarah O’Connor")
    assert result.requires_review
    assert len(result.mentions) == 4
    assert result.mentions[-1].paragraph == 3
    assert result.mentions[-1].timestamp == "[00:00:40]"
    assert all(not name.endswith("*") for name in result.names)


@pytest.mark.parametrize("text,names", [
    ("I am joined for this session by Herbie Hancock.", ("Herbie Hancock",)),
    ("Please welcome Alexandra. Mohammed, thank you for being here.", ("Alexandra", "Mohammed")),
    ("We discussed Andra\u0301s Sza\u0301nto\u0301 and Jean-Luc O’Neill.", ("András Szántó", "Jean-Luc O’Neill")),
    ("Panos A Panay spoke with Farah Al Qassimi.", ("Panos A Panay", "Farah Al Qassimi")),
    ("Our guests are Jane Smith and John Doe.", ("Jane Smith", "John Doe")),
    ("Hello, I'm Er Zhang, director.", ("Er Zhang",)),
])
def test_generic_name_mentions_and_partial_names(text, names):
    assert extract_transcript((TranscriptParagraph(1, text),)).names == names


@pytest.mark.parametrize("text", [
    "Welcome to the Culture Summit. Our panel will begin soon.",
    "We work at Louvre Abu Dhabi and New York University.",
    "Speaker 78: Hello. Speaker 140: Thank you.",
    "Our report is called The Museum in an Expanded Field.",
    "The United Nations and European Commission presented a report.",
])
def test_labels_organizations_and_generic_topics_do_not_become_names(text):
    result = extract_transcript((TranscriptParagraph(1, text),))
    assert result.status != "found"
    assert not result.names


def test_each_transcript_name_is_marked_in_review_and_csv_only(tmp_path):
    path = docx(tmp_path / "05. Talk.docx", [["[00:00:01] Speaker 7: I'm Jane Smith, curator. Please welcome John Doe."]])
    original = path.read_bytes()
    table = imported()
    review = SpeakerReview(table)
    proposal = SpeakerExtractor(TranscriptIndex(tmp_path)).extract_all(table)[0]
    assert proposal.name == "Jane Smith; John Doe"
    assert proposal.proposed_value == "Jane Smith*; John Doe*"
    review.offer([proposal])
    assert review.editor_rows()[0]["Speakers"] == "Jane Smith*; John Doe*"
    review.approve()
    records = list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))
    assert records[1][3] == "Jane Smith*; John Doe*"
    assert records[2][3] == "Keep existing*"
    assert records[1][-1] == "0005"
    assert path.read_bytes() == original
    review.edit({0: "Jane Smith; John Doe"})
    assert not review.ready
    review.approve()
    assert "*" not in list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))[1][3]


@pytest.mark.parametrize("title,caption", [("Keynote by Jane Smith", "No description"),
                                         ("Generic topic", "Main speaker: Jane Smith")])
def test_title_and_caption_successes_do_not_receive_stars_or_open_docx(tmp_path, title, caption):
    table = imported(title, caption)
    index = TranscriptIndex(tmp_path)
    proposal = SpeakerExtractor(index).extract_all(table)[0]
    assert proposal.proposed_value == "Jane Smith"
    assert not proposal.detection.requires_review
    assert not index.loaded


def test_explicitly_cleared_or_edited_starred_value_survives_new_extraction(tmp_path):
    docx(tmp_path / "05. Talk.docx", [["I'm Jane Smith, director."]])
    table = imported()
    extractor = SpeakerExtractor(TranscriptIndex(tmp_path))
    review = SpeakerReview(table)
    review.offer(extractor.extract_all(table))
    assert review.values()[0] == "Jane Smith*"
    for value in ("", "Reviewed Person"):
        review.edit({0: value})
        review.offer(extractor.extract_all(table))
        assert review.values()[0] == value
