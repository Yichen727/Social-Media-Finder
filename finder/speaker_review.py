"""Review speaker proposals and export approved cells without changing source data."""

from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass, field
import io

from finder.speaker_extract import SpeakerProposal
from finder.speaker_import import SpeakerCSV


@dataclass
class SpeakerReview:
    table: SpeakerCSV
    proposals: dict[int, SpeakerProposal] = field(default_factory=dict)
    edits: dict[int, str] = field(default_factory=dict)
    approved: dict[int, str] | None = None

    def offer(self, proposals: Iterable[SpeakerProposal]) -> None:
        """Refresh machine suggestions while retaining every manual override."""
        offered = {}
        for proposal in proposals:
            if proposal.row_id in offered or not 0 <= proposal.row_id < len(self.table.rows):
                raise ValueError("Proposal row identities must match the imported CSV.")
            row = self.table.rows[proposal.row_id]
            if (proposal.reference != row.reference
                    or proposal.original_value != row.values[self.table.speaker_column]):
                raise ValueError("The proposal belongs to a different source row.")
            offered[proposal.row_id] = proposal
        self.proposals = offered

    def values(self) -> dict[int, str]:
        values = {}
        for row in self.table.eligible_rows:
            value = row.values[self.table.speaker_column]
            proposal = self.proposals.get(row.row_id)
            if not row.has_speaker and proposal and proposal.status == "found":
                value = proposal.proposed_value
            values[row.row_id] = self.edits.get(row.row_id, value)
        return values

    def edit(self, values: Mapping[int, str]) -> None:
        """Accept edits by original row ID, never by reference or display order."""
        current = self.values()
        if any(row_id not in current or not isinstance(value, str) for row_id, value in values.items()):
            raise ValueError("Only speaker text in eligible numbered rows can be edited.")
        for row_id, value in values.items():
            if value != current[row_id]:
                self.edits[row_id] = value

    def editor_rows(self) -> list[dict]:
        values = self.values()
        return [
            {"_row_id": row.row_id, "Ref Number": row.values[self.table.reference_column],
             "High-res video name": row.values.get(self.table.video_name_column, ""),
             "Speakers": values[row.row_id]}
            for row in self.table.eligible_rows
        ]

    def approve(self) -> None:
        self.approved = self.values()

    @property
    def ready(self) -> bool:
        return self.approved is not None and self.approved == self.values()

    def reset(self) -> None:
        """Explicitly discard manual edits/approval, retaining the latest suggestions."""
        self.edits.clear()
        self.approved = None

    def export_csv(self) -> bytes:
        if not self.ready:
            raise ValueError("Apply reviewed changes before downloading the completed CSV.")
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=self.table.delimiter, lineterminator="\r\n")
        writer.writerow(self.table.headers)
        speaker_index = self.table.headers.index(self.table.speaker_column)
        for row in self.table.rows:
            cells = list(row.cells)
            if row.eligible:
                cells[speaker_index] = self.approved[row.row_id]
            writer.writerow(cells)
        return output.getvalue().encode("utf-8-sig")
