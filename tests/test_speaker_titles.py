import csv
import io
from unittest.mock import Mock

import pytest

from finder.speaker_extract import SpeakerExtractor, extract_title
from finder.speaker_import import TranscriptIndex, load_speaker_csv
from finder.speaker_review import SpeakerReview


FEEDBACK = [
    (13, "Creative Conversation with Maja Hoffmann & Hashim Sarkis-Creative Alliances for a Sustainable World.mp4", ("Maja Hoffmann", "Hashim Sarkis")),
    (25, "Rita Wilson’s Liner Notes Featuring the Names Behind the Hits.mp4", ("Rita Wilson",)),
    (26, "Creative Conversations_ Ai Da in conversation with Tim Marlow _ تيم مارلو في حوار مع الروبوت »آي-دا«.mp4", ("Ai Da", "Tim Marlow")),
    (30, "Creative Conversations_ Eddie Opara and Huda AbiFares in conversation with Sumitra Upham.mp4", ("Eddie Opara", "Huda AbiFares", "Sumitra Upham")),
    (36, "Art, Data, and the Imagination_ A Creative Conversation with Refik Anadol and Ralph Nauta.mp4", ("Refik Anadol", "Ralph Nauta")),
    (41, "Sumayya Vally in conversation with Tim Marlow _ سمية فالي في حوار مع تيم مارلو.mp4", ("Sumayya Vally", "Tim Marlow")),
    (42, "Creative conversation with Kader Attia _ حوارات إبداعية مع قادر عطية.mp4", ("Kader Attia",)),
    (47, "Creative Conversation with Michael Uslan and David Uslan _ حوارات إبداعية مع ميشال وديفيد أوسلان.mp4", ("Michael Uslan", "David Uslan")),
    (53, "Creative conversation with David Henry Hwang and Rana Kazkaz.mp4", ("David Henry Hwang", "Rana Kazkaz")),
]


def table_for(title, reference=5):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Ref Number", "High-res video name", "YouTube Caption", "Speakers"])
    writer.writerow([reference, title, "Main speaker: Unrelated Person", ""])
    return load_speaker_csv(output.getvalue().encode("utf-8-sig"))


@pytest.mark.parametrize("reference,title,names", FEEDBACK)
def test_user_reported_titles_extract_every_expected_name_and_stop(reference, title, names):
    table = table_for(title, reference)
    index = Mock(spec=TranscriptIndex)
    extractor = SpeakerExtractor(index)
    extractor.extract_caption = Mock(side_effect=AssertionError("Caption must be skipped"))
    proposal = extractor.extract_all(table)[0]
    assert proposal.status == "found"
    assert proposal.detection.names == names
    assert proposal.proposed_value == "; ".join(names)
    assert proposal.detection.evidence == title
    assert len(proposal.attempts) == 1
    index.lookup.assert_not_called()
    extractor.extract_caption.assert_not_called()


@pytest.mark.parametrize("title,names", [
    ("Creative Conversation with Maja Hoffmann AND Hashim Sarkis.mp4", ("Maja Hoffmann", "Hashim Sarkis")),
    ("Creative Conversation with Maja Hoffmann, Hashim Sarkis & Jane Smith.mp4", ("Maja Hoffmann", "Hashim Sarkis", "Jane Smith")),
    ("Architecture _ A Creative Conversation with Refik Anadol and Ralph Nauta.mp4", ("Refik Anadol", "Ralph Nauta")),
    ("Screening + Conversation_ Christopher Kulendran Thomas with X Zhu-Nowell.mp4", ("Christopher Kulendran Thomas", "X Zhu-Nowell")),
    ("Panos A  Panay in conversation with Jimmy Jam.mp4", ("Panos A Panay", "Jimmy Jam")),
    ("Creative Conversations_ Tatiana Bilbao and Asif Khan in conversation with Tim Marlow.mp4", ("Tatiana Bilbao", "Asif Khan", "Tim Marlow")),
    ("Rita Wilson's Liner Notes Featuring the Names Behind the Hits.mp4", ("Rita Wilson",)),
    ("Creative Conversations_ Ai-Da in conversation with Tim Marlow.mp4", ("Ai-Da", "Tim Marlow")),
    ("Creative Conversations_ Ai Da.mp4", ("Ai Da",)),
    ("Creative Conversation with Jean-Luc O’Neill & X Zhu-Nowell.mp4", ("Jean-Luc O’Neill", "X Zhu-Nowell")),
    ("Keynote by H.E. Ali bin Tamim and Andra\u0301s Sza\u0301nto\u0301 - The Future.mp4", ("H.E. Ali bin Tamim", "András Szántó")),
    ("Creative Conversation with Jane Smith & JANE SMITH.mp4", ("Jane Smith",)),
    ("Keynote by Jane Smith: A Talk about Culture.mp4", ("Jane Smith",)),
])
def test_title_formats_preserve_names_order_and_unicode(title, names):
    result = extract_title(title)
    assert result.status == "found"
    assert result.names == names
    assert result.name == "; ".join(names)


@pytest.mark.parametrize("title", [
    "Creative Conversation with Maja Hoffmann & .mp4",
    "Creative Conversation with Maja Hoffmann and Hashim Sarki?.mp4",
    "Creative Conversation with Jane Smith and Creative Community.mp4",
    "Artist Talk_ Jatiwangi Art Factory with X Zhu-Nowell.mp4",
    "Artist Talk_ BAIT١٥ - Serving the Community.mp4",
    "A Conversation_ About Jazz, Humanity and Beyond.mp4",
    "Art, Data, and the Imagination.mp4",
    "People and Place.mp4",
    "Louvre Abu Dhabi’s Liner Notes.mp4",
    "Alexandra in conversation with Mohammed.mp4",
])
def test_unsafe_or_incomplete_title_lists_do_not_fill_partial_people(title):
    assert extract_title(title).status != "found"


def test_multiple_names_are_reviewed_and_exported_in_one_cell_without_column_changes():
    title = FEEDBACK[3][1]
    table = table_for(title, 30)
    review = SpeakerReview(table)
    review.offer(SpeakerExtractor().extract_all(table))
    assert not review.ready
    assert review.values()[0] == "Eddie Opara; Huda AbiFares; Sumitra Upham"
    review.approve()
    records = list(csv.reader(io.StringIO(review.export_csv().decode("utf-8-sig"))))
    assert records[0] == list(table.headers)
    assert records[1] == ["30", title, "Main speaker: Unrelated Person", "Eddie Opara; Huda AbiFares; Sumitra Upham"]
