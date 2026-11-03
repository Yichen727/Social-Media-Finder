"""Read-only CSV import and lazy transcript matching for numbered talks.

This module does not extract names, read DOCX contents, or make network requests.
"""

from collections import Counter, defaultdict
from collections.abc import Collection
import csv
from dataclasses import dataclass
import io
import os
from pathlib import Path
import re

NUMBERED_TALKS = frozenset(range(1, 94))
DELIMITERS = (",", ";", "\t", "|")


class SpeakerImportError(ValueError):
    """An input cannot be imported without guessing or losing source data."""


def _header(value: str) -> str:
    return " ".join(value.split()).casefold()


def normalize_reference(value: str) -> int | None:
    value = value.strip()
    if not re.fullmatch(r"[0-9]+", value):
        return None
    digits = value.lstrip("0")
    if not digits or len(digits) > 9:
        return None
    return int(digits)


@dataclass(frozen=True)
class SpeakerRow:
    row_id: int
    headers: tuple[str, ...]
    cells: tuple[str, ...]
    reference: int | None
    issue: str | None
    has_speaker: bool

    @property
    def values(self) -> dict[str, str]:
        # Callers may edit this copy without changing the original imported cells.
        return dict(zip(self.headers, self.cells))

    @property
    def eligible(self) -> bool:
        return self.reference is not None and self.issue is None

    @property
    def needs_speaker(self) -> bool:
        return self.eligible and not self.has_speaker


@dataclass(frozen=True)
class SpeakerCSV:
    headers: tuple[str, ...]
    rows: tuple[SpeakerRow, ...]
    encoding: str
    delimiter: str
    reference_column: str
    speaker_column: str
    video_name_column: str | None
    caption_column: str | None
    bom: bytes = b""

    @property
    def eligible_rows(self) -> tuple[SpeakerRow, ...]:
        return tuple(row for row in self.rows if row.eligible)

    @property
    def pending_rows(self) -> tuple[SpeakerRow, ...]:
        return tuple(row for row in self.rows if row.needs_speaker)

    def to_csv_bytes(self) -> bytes:
        """Round-trip source values in the detected input encoding; never write a file."""
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=self.delimiter, lineterminator="\r\n")
        writer.writerow(self.headers)
        writer.writerows(row.cells for row in self.rows)
        return self.encode_csv(output.getvalue())

    def encode_csv(self, text: str) -> bytes:
        """Retain the source encoding, including UTF-8 BOM and UTF-16 byte order."""
        encoded = text.encode(self.encoding)
        return self.bom + encoded if self.encoding in {"utf-16-le", "utf-16-be"} else encoded


def _decode(data: bytes, encoding: str | None) -> tuple[str, str]:
    choices = (encoding,) if encoding else (
        ("utf-16-le",) if data.startswith(b"\xff\xfe") else
        ("utf-16-be",) if data.startswith(b"\xfe\xff") else
        ("utf-8-sig", "cp1252") if data.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252")
    )
    for choice in choices:
        try:
            text = data.decode(choice)
        except LookupError as exc:
            raise SpeakerImportError(f"Unknown CSV encoding: {choice}.") from exc
        except UnicodeError:
            continue
        if "\x00" in text:
            raise SpeakerImportError("The CSV contains null characters. Check the selected encoding.")
        return text.removeprefix("\ufeff"), choice
    raise SpeakerImportError("The CSV could not be decoded. Choose the file's encoding explicitly.")


def _delimiter(text: str) -> str:
    # Recognizing the required header is more reliable than sniffing long captions.
    matches = []
    for delimiter in DELIMITERS:
        try:
            headers = next(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
        except (csv.Error, StopIteration):
            continue
        if "ref number" in {_header(value) for value in headers}:
            matches.append((delimiter, headers))
    if not matches:
        raise SpeakerImportError("Could not find Ref Number. Check the header and CSV delimiter.")
    if len({tuple(headers) for _, headers in matches}) != 1:
        raise SpeakerImportError("The CSV delimiter is ambiguous. Select it explicitly.")
    return matches[0][0]


def load_speaker_csv(data: bytes, *, encoding: str | None = None, delimiter: str | None = None,
                     speaker_column: str | None = None,
                     allowed_references: Collection[int] = NUMBERED_TALKS) -> SpeakerCSV:
    """Import uploaded bytes, preserving cells and restricting eligibility to refs 1–93."""
    text, detected_encoding = _decode(data, encoding)
    chosen_delimiter = delimiter if delimiter is not None else _delimiter(text)
    if chosen_delimiter not in DELIMITERS:
        raise SpeakerImportError("Choose a comma, semicolon, tab, or pipe delimiter.")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=chosen_delimiter, strict=True)
    try:
        source_headers = next(reader)
        if not source_headers or any(not header.strip() for header in source_headers):
            raise SpeakerImportError("Every CSV column must have a nonblank header.")
        names = {_header(header): header for header in source_headers}
        if len(names) != len(source_headers):
            raise SpeakerImportError("CSV headers must be unique, ignoring case and whitespace.")
        if "ref number" not in names:
            raise SpeakerImportError("The CSV needs a Ref Number column.")
        speaker_headers = [names[name] for name in ("speaker", "speakers") if name in names]
        if speaker_column is not None:
            selected = names.get(_header(speaker_column))
            if selected not in speaker_headers:
                raise SpeakerImportError("Select an existing Speaker or Speakers column.")
        elif len(speaker_headers) > 1:
            raise SpeakerImportError("Both Speaker and Speakers exist. Choose speaker_column explicitly.")
        else:
            selected = speaker_headers[0] if speaker_headers else "Speakers"
        add_speaker = not speaker_headers
        headers = tuple(source_headers + ([selected] if add_speaker else []))
        records = []
        for record in reader:
            if not record:
                continue
            if len(record) != len(source_headers):
                raise SpeakerImportError(
                    f"CSV record ending at line {reader.line_num} has {len(record)} cells; "
                    f"expected {len(source_headers)}. No columns were shifted or discarded."
                )
            records.append(tuple(record + ([""] if add_speaker else [])))
    except StopIteration as exc:
        raise SpeakerImportError("The CSV is empty.") from exc
    except csv.Error as exc:
        raise SpeakerImportError(f"Invalid CSV near line {reader.line_num}: {exc}") from exc

    reference_index = headers.index(names["ref number"])
    speaker_index = headers.index(selected)
    references = [normalize_reference(record[reference_index]) for record in records]
    allowed = frozenset(allowed_references)
    counts = Counter(ref for ref in references if ref in allowed)
    rows = []
    for row_id, (record, reference) in enumerate(zip(records, references)):
        original_ref = record[reference_index]
        issue = None
        if not original_ref.strip():
            issue = "missing_reference"
        elif reference is None:
            issue = "invalid_reference"
        elif reference not in allowed:
            issue = "out_of_scope"
        elif counts[reference] > 1:
            issue = "duplicate_reference"
        rows.append(SpeakerRow(row_id, headers, record, reference, issue, bool(record[speaker_index].strip())))
    return SpeakerCSV(headers, tuple(rows), detected_encoding, chosen_delimiter, names["ref number"],
                      selected, names.get("high-res video name"), names.get("youtube caption"),
                      bom=data[:2] if data.startswith((b"\xff\xfe", b"\xfe\xff")) else b"")


@dataclass(frozen=True)
class TranscriptMatch:
    reference: int | None
    status: str
    paths: tuple[Path, ...] = ()
    message: str = ""

    @property
    def path(self) -> Path | None:
        return self.paths[0] if self.status == "matched" else None


class TranscriptIndex:
    """Scan filenames only on the first lookup; never open a DOCX file."""

    def __init__(self, folder: str | Path, *, allowed_references: Collection[int] = NUMBERED_TALKS):
        self.folder = Path(folder).expanduser() if str(folder).strip() else None
        self.allowed_references = frozenset(allowed_references)
        self.refresh()

    def refresh(self):
        """Invalidate cached metadata; the next lookup will scan the folder again."""
        self.loaded = False
        self._matches = defaultdict(list)
        self._conflicts = defaultdict(list)
        self._error = ""

    def _hint(self, name: str) -> int | None:
        match = re.match(r"^([0-9]+)(?:[.\s_-]|$)", name)
        reference = normalize_reference(match[1]) if match else None
        return reference if reference in self.allowed_references else None

    def _load(self):
        self.loaded = True
        try:
            if self.folder is None or not self.folder.is_dir():
                self._error = "Select an accessible transcript folder."
                return
            root = self.folder.resolve()
            root_ref = self._hint(root.name)
            errors = []
            for directory, subfolders, filenames in os.walk(root, onerror=errors.append, followlinks=False):
                subfolders[:] = sorted(name for name in subfolders if not name.startswith(".") and name != "__MACOSX")
                for name in sorted(filenames):
                    if not name.lower().endswith(".docx") or name.startswith(("~$", ".")):
                        continue
                    path = Path(directory) / name
                    if path.is_symlink():
                        continue
                    file_ref = self._hint(path.stem)
                    folder_refs = {root_ref, *(self._hint(part) for part in path.relative_to(root).parts[:-1])} - {None}
                    hints = folder_refs | ({file_ref} if file_ref is not None else set())
                    if len(hints) > 1:
                        for reference in hints:
                            self._conflicts[reference].append(path)
                    elif hints:
                        self._matches[hints.pop()].append(path)
            if errors:
                self._error = "Some transcript folders could not be read: " + str(errors[0])
        except OSError as exc:
            self._error = f"The transcript folder could not be indexed: {exc}"

    def lookup(self, reference: str | int) -> TranscriptMatch:
        ref = normalize_reference(str(reference))
        if ref not in self.allowed_references:
            return TranscriptMatch(ref, "invalid_reference", message="Use an in-scope numbered talk reference.")
        if not self.loaded:
            self._load()
        if self._error:
            return TranscriptMatch(ref, "folder_error", message=self._error)
        paths = tuple(self._matches.get(ref, ()))
        conflicts = tuple(self._conflicts.get(ref, ()))
        if conflicts:
            return TranscriptMatch(ref, "conflicting_reference", paths + conflicts,
                                   "Filename and folder references disagree. No file was selected.")
        if not paths:
            return TranscriptMatch(ref, "missing", message="No matching DOCX file was found.")
        if len(paths) > 1:
            return TranscriptMatch(ref, "duplicate", paths, "Multiple matching DOCX files were found. No file was selected.")
        return TranscriptMatch(ref, "matched", paths)
