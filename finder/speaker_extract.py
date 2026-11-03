"""Deterministic speaker proposals: video title, CSV caption, then DOCX.

No network/model calls or source-file writes. Ambiguous participation stays blank.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from finder.speaker_import import SpeakerCSV, SpeakerRow, TranscriptIndex

HONORIFICS = frozenset("dr dr. prof prof. professor sir dame he h.e. h.e sheikh sheikha his excellency her excellency".split())
PARTICLES = frozenset("al el bin ibn bint de del della der di da dos du la le van von den ten".split())
SUFFIXES = frozenset("jr jr. sr sr. cbe obe mbe".split())
ORGANIZATIONS = frozenset("museum museums university college school institute foundation ministry department organisation organization company studios factory collective".split())
NOT_NAMES = frozenset((
    "a an the i i'm am my name is we our you your he she they it this that today tomorrow "
    "hello hi thank thanks good morning afternoon evening welcome please friend colleague "
    "speaker speakers presenter moderator panel panelists panelist director curator senior "
    "president founder chief executive secretary minister assistant head partner artist artists "
    "author writer museum museums university college school institute foundation ministry "
    "department organisation organization company studios factory collective guggenheim louvre "
    "berklee unesco unctad ifacca culture cultural summit community practice creative creativity "
    "conversation conversations keynote talk space public digital future futures art arts "
    "innovation time humanity knowledge intervention sustainability leadership expression "
    "information technology machine music world challenges opportunities building people"
).split())
WORD = re.compile(r"[^\W\d_]+(?:[’'\-.][^\W\d_]+)*\.?\Z", re.UNICODE)
TITLE_PREFIX = re.compile(
    r"\b(?:keynote(?:\s+(?:address|speech|conversation))?\s+(?:by|with)\s+|"
    r"(?:a\s+)?(?:creative\s+)?conversations?\s+with\s+|"
    r"(?:creative\s+conversations?|keynote\s+conversations?|artist\s+talk|"
    r"screening\s*\+\s*conversation)\s*[:_]\s*|a\s+keynote\s+(?:by\s+)?)", re.I
)
TITLE_CONVERSATION = re.compile(r"\s+in\s+conversation\s+with\s+", re.I)
TITLE_NAMES = re.compile(r"\s+in\s+conversation\s+with\s+|\s+(?:and|with)\s+|\s*&\s*|\s*[,;]\s*", re.I)
TITLE_END = re.compile(r"\s+[_|]\s+|\s+[–—-]\s+|[–—]|-(?=(?:creative|the|a|an)\b)|:", re.I)
SELF_INTRO = re.compile(r"\b(?:my\s+name\s+is|I\s+am|I'm|I’m)\s*[,;:]?\s+", re.I)
TIMESTAMP = re.compile(r"^\s*\[(\d{2}):(\d{2}):(\d{2})\]\s*")
SPEAKER_LABEL = re.compile(r"^\s*Speaker\s+([0-9]+)\s*:\s*", re.I)
GROUP = re.compile(r"\b(?:panel(?:ists?|\s+discussion)?|moderator|moderating|moderated|speakers(?=\s*:)|joined\s+by|our\s+guests|my\s+guests|fellow\s+panelists)\b", re.I)
INTRODUCER = re.compile(r"\b(?:introduc(?:e|ing)\s+(?:you|our|the\s+(?:speaker|guest))|moderate\s+(?:this|the))\b", re.I)
UNAVAILABLE = frozenset({"", "no description", "no description available", "none", "n/a", "na", "null", "not available", "-"})


@dataclass(frozen=True)
class Detection:
    source: str
    status: str
    name: str = ""
    evidence: str = ""
    reason: str = ""
    path: Path | None = None
    paragraph: int | None = None
    timestamp: str = ""
    speaker_label: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        """Names in the automatic semicolon format; never split existing CSV cells."""
        return tuple(name.strip() for name in self.name.split(";") if name.strip())


@dataclass(frozen=True)
class SpeakerProposal:
    row_id: int
    reference: int | None
    original_value: str
    status: str
    attempts: tuple[Detection, ...] = ()

    @property
    def detection(self) -> Detection | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def name(self) -> str:
        return self.detection.name if self.status == "found" and self.detection else ""

    @property
    def proposed_value(self) -> str:
        return self.name if self.status == "found" else self.original_value


@dataclass(frozen=True)
class TranscriptParagraph:
    index: int
    text: str
    timestamp: str = ""
    seconds: int | None = None
    speaker_label: str = ""


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _without_fillers(text: str) -> str:
    text = _normalized(text)
    return re.sub(r"[,;]\s*(?:uh|um|er|ah)\s*[,;]\s*", " ", text, flags=re.I)


def _name_prefix(text: str, *, mononym: bool = False, initials: bool = False) -> str:
    segment = re.split(r"[,;:\n|]|\s+[–—-]\s+", text, maxsplit=1)[0].strip()
    if "?" in segment or "\ufffd" in segment:
        return ""
    if any(token.strip(".").casefold() in ORGANIZATIONS for token in segment.split()):
        return ""
    parts = []
    for raw in segment.split():
        token = raw.strip('"“”‘’()[]')
        lower = token.casefold()
        middle_initial = initials and bool(parts) and len(token) == 1 and token.isupper()
        if (lower in NOT_NAMES - HONORIFICS and not middle_initial) or lower in {"and", "with", "in", "from", "who", "will"}:
            break
        if not WORD.fullmatch(token) and lower not in HONORIFICS:
            break
        if token[0].islower() and lower not in PARTICLES | SUFFIXES:
            break
        parts.append(token)
        if token.endswith(".") and len(token.rstrip(".")) > 1 and lower not in HONORIFICS | SUFFIXES:
            parts[-1] = token.rstrip(".")
            break
    if not parts or len(parts) > 14:
        return ""
    meaningful = [part for part in parts if part.casefold() not in HONORIFICS | PARTICLES | SUFFIXES]
    if len(meaningful) < 2:
        if not meaningful:
            return ""
        token = meaningful[0]
        non_latin = all(ord(char) > 127 for char in token) and len(token) >= 2
        if not (mononym or non_latin or token.isupper() and len(token) >= 3):
            return ""
    return " ".join(parts)


def _multiple_names(text: str) -> bool:
    # Restrict to the attributed phrase, not names in later prose or other sections.
    text = re.split(r"\s+[–—-]\s+|[|\n]", text, maxsplit=1)[0]
    segments = re.split(r"[,;]", text)
    if any(_name_prefix(segment.strip()) for segment in segments[1:]):
        return True
    text = segments[0]
    if re.search(r"\bin\s+conversation\s+with\b", text, re.I):
        return True
    return any(_name_prefix(text[match.end():], mononym=True)
               for match in re.finditer(r"\b(?:and|with)\s+|&\s*", text, re.I))


def _selection(source: str, candidates, *, ambiguous: bool = False) -> Detection:
    unique = {}
    for name, evidence in candidates:
        unique.setdefault(name.casefold(), (name, evidence))
    if ambiguous or len(unique) > 1:
        return Detection(source, "ambiguous", reason="Several people or unclear main-speaker roles were found.")
    if unique:
        name, evidence = next(iter(unique.values()))
        return Detection(source, "found", name, evidence)
    return Detection(source, "not_found", reason="No supported main-speaker name was found.")


def extract_title(text: str) -> Detection:
    """Extract explicitly named title participants, keeping their source order."""
    source = "video_title"
    if text.strip().casefold() in UNAVAILABLE:
        return Detection(source, "unavailable", reason="The video title is empty.")
    title = _normalized(re.sub(r"\.(?:mp4|mov|mkv|webm|avi)\s*$", "", text, flags=re.I))
    prefix = TITLE_PREFIX.search(title)
    if prefix and re.search(r"\bin\s+$", title[:prefix.start()], re.I):
        prefix = None  # Keep both sides of an unprefixed "A in conversation with B".
    mononym = bool(prefix)
    if prefix:
        attributed = title[prefix.end():]
    elif TITLE_CONVERSATION.search(title):
        attributed = title
    else:
        owner = re.match(r"^(.+?)[’']s\s+liner\s+notes\b", title, re.I)
        if owner:
            attributed = owner[1]
        elif re.match(r"^(?:Sir|Dame|Dr\.?|Prof\.?|H\.?E\.?|Sheikh|Sheikha)\s+", title, re.I):
            attributed = title
        else:
            return Detection(source, "not_found", reason="The title does not explicitly identify speaker names.")
    attributed = TITLE_END.split(attributed, maxsplit=1)[0].strip()
    names = {}
    for fragment in TITLE_NAMES.split(attributed):
        fragment = fragment.strip().strip('"“”‘’()[]')
        name = _name_prefix(fragment, mononym=mononym, initials=True)
        # Do not turn an organization, damaged name, topic, or incomplete list
        # into a partial personal name merely because its prefix looks valid.
        if not name or name != fragment:
            return Detection(source, "ambiguous", reason="A title participant is not a complete supported person name.")
        names.setdefault(name.casefold(), name)
    if not names:
        return Detection(source, "not_found", reason="The title contains no supported person names.")
    return Detection(source, "found", "; ".join(names.values()), text)


def extract_caption(text: str) -> Detection:
    """Require a main-speaker attribution, rather than any name in a description."""
    source = "youtube_caption"
    if _normalized(text).casefold() in UNAVAILABLE:
        return Detection(source, "unavailable", reason="No usable YouTube Caption was supplied.")
    candidates = []
    ambiguous = False
    cues = (
        r"\b(?:main|featured|keynote)\s+(?:speaker|presenter)\s*[:–—-]\s*",
        r"\bkeynote(?:\s+(?:address|speech|conversation))?\s+(?:by|with)\s+",
        r"\b(?:in|during)\s+(?:a|the|his|her)\s+keynote(?:\s+(?:address|speech))?\s*,\s*",
        r"\bcreative\s+conversation\s+with\s+",
    )
    for cue in cues:
        for match in re.finditer(cue, text, re.I):
            tail = text[match.end():]
            name = _name_prefix(tail, mononym="keynote" in match[0].casefold())
            if _multiple_names(tail):
                ambiguous = True
            elif name:
                start = text.rfind("\n", 0, match.start()) + 1
                end = text.find("\n", match.end())
                candidates.append((name, text[start:end if end >= 0 else len(text)].strip()))
    result = _selection(source, candidates, ambiguous=ambiguous)
    if result.status == "not_found" and re.search(r"\b(?:speakers|panelists|moderated\s+by|moderator)\s*[:\n]?", text, re.I):
        return Detection(source, "ambiguous", reason="A moderator or participant list does not establish one main speaker.")
    return result


def _main_mentions(text: str):
    candidates = []
    ambiguous = False
    for cue in (
        r"\b(?:our|the|today's)?\s*(?:main|keynote|featured)\s+(?:speaker|presenter)\s*(?:is\s+|[:,–—-]\s*)?",
        r"\b(?:discussion|conversation|interview)\s+with\s+(?:the|our)\s+(?:artist|author|filmmaker)\s*,?\s*",
    ):
        for match in re.finditer(cue, text, re.I):
            context = re.split(r"[.!?]\s+", text[:match.start()])[-1]
            if re.search(r"\b(?:yesterday|previous|earlier|last\s+year|next\s+year)\b", context, re.I):
                continue
            tail = text[match.end():]
            name = _name_prefix(tail)
            if _multiple_names(tail):
                ambiguous = True
            elif name:
                candidates.append(name)
    if re.search(r"\b(?:introduce|introducing|welcome)\b", text, re.I):
        giving = r"\b(?:who\s+)?will\s+(?:be\s+)?(?:giving|give|delivering|deliver|presenting|present)\s+(?:a|the|his|her)\s+(?:talk|keynote|address|presentation)\b"
        for match in re.finditer(giving, text, re.I):
            left = text[max(0, match.start() - 180):match.start()].rstrip(" ,")
            left = re.split(r"[,;:]", left)[-1]
            words = left.split()
            for start in range(len(words)):
                fragment = " ".join(words[start:])
                name = _name_prefix(fragment)
                if name and name == fragment.strip():
                    candidates.append(name)
                    break
    return candidates, ambiguous


def extract_transcript(paragraphs: tuple[TranscriptParagraph, ...], path: Path | None = None,
                       *, session_context: str = "") -> Detection:
    source = "transcript"
    if not paragraphs:
        return Detection(source, "unavailable", reason="The transcript opening contains no usable text.", path=path)
    featured = []
    self_names = []
    featured_ambiguous = False
    # Already-attempted CSV fields can establish a panel even when its moderator
    # spends the entire bounded DOCX opening speaking alone.
    group = bool(GROUP.search(session_context.replace("_", " ")))
    introducer = False
    labels = set()
    metadata = {}
    for paragraph in paragraphs:
        text = _without_fillers(paragraph.text)
        if re.match(r"^\d+\.\s", text):
            continue  # Document headings are not spoken introductions.
        names, ambiguous = _main_mentions(text)
        featured_ambiguous |= ambiguous
        for name in names:
            featured.append((name, paragraph.text))
            metadata.setdefault(name.casefold(), paragraph)
        for match in SELF_INTRO.finditer(text):
            name = _name_prefix(text[match.end():])
            if name:
                self_names.append((name, paragraph.text))
                metadata.setdefault(name.casefold(), paragraph)
        group |= bool(GROUP.search(text))
        introducer |= bool(INTRODUCER.search(text))
        if paragraph.speaker_label:
            labels.add(paragraph.speaker_label)
    if featured or featured_ambiguous:
        selected = _selection(source, featured, ambiguous=featured_ambiguous)
    elif group or introducer or len(labels) > 1:
        selected = Detection(source, "ambiguous", reason="The opening describes a panel, introducer, or multiple unidentified roles.")
    else:
        selected = _selection(source, self_names)
    if selected.status != "found":
        return Detection(source, selected.status, reason=selected.reason, path=path)
    paragraph = metadata[selected.name.casefold()]
    return Detection(source, "found", selected.name, selected.evidence, path=path,
                     paragraph=paragraph.index, timestamp=paragraph.timestamp, speaker_label=paragraph.speaker_label)


class SpeakerExtractor:
    """Reusable local extractor; returns proposals without editing imported rows."""

    def __init__(self, transcripts: TranscriptIndex | None = None, *, max_seconds: int = 180,
                 max_chars: int = 8000, max_paragraphs: int = 40):
        self.transcripts = transcripts
        self.max_seconds = max_seconds
        self.max_chars = max_chars
        self.max_paragraphs = max_paragraphs
        self._opening_cache = {}

    extract_title = staticmethod(extract_title)
    extract_caption = staticmethod(extract_caption)

    def read_opening(self, path: Path) -> tuple[TranscriptParagraph, ...]:
        """Join DOCX text runs and cache bounded, complete opening paragraphs."""
        path = Path(path).resolve()
        info = path.stat()
        version = (info.st_mtime_ns, info.st_size, self.max_seconds, self.max_chars, self.max_paragraphs)
        cached = self._opening_cache.get(path)
        if cached and cached[0] == version:
            return cached[1]
        paragraphs = []
        characters = 0
        index = 0
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with ZipFile(path) as document:
            entry = document.getinfo("word/document.xml")
            if entry.file_size > 16 * 1024 * 1024:
                raise ValueError("The DOCX document XML exceeds the reading limit.")
            with document.open(entry) as stream:
                for _, node in ET.iterparse(stream, events=("end",)):
                    if node.tag != ns + "p":
                        continue
                    index += 1
                    raw = "".join((part.text or "") if part.tag == ns + "t" else "\n"
                                  for part in node.iter() if part.tag in {ns + "t", ns + "br", ns + "tab"}).strip()
                    node.clear()
                    if not raw:
                        continue
                    stop = False
                    for fragment in re.split(r"(?=\[\d{2}:\d{2}:\d{2}\])", raw):
                        if not fragment.strip():
                            continue
                        stamp = TIMESTAMP.match(fragment)
                        if stamp and (int(stamp[2]) >= 60 or int(stamp[3]) >= 60):
                            raise ValueError("A transcript timestamp is invalid.")
                        timestamp = stamp[0].strip() if stamp else ""
                        seconds = int(stamp[1]) * 3600 + int(stamp[2]) * 60 + int(stamp[3]) if stamp else None
                        spoken = fragment[stamp.end():] if stamp else fragment
                        label = SPEAKER_LABEL.match(spoken)
                        if label:
                            spoken = spoken[label.end():]
                        if ((seconds is not None and seconds > self.max_seconds)
                                or len(paragraphs) >= self.max_paragraphs
                                or characters + len(spoken) > self.max_chars):
                            stop = True
                            break  # Never manufacture a name from a cut-off paragraph.
                        paragraphs.append(TranscriptParagraph(index, unicodedata.normalize("NFC", spoken), timestamp,
                                                              seconds, label[1] if label else ""))
                        characters += len(spoken)
                    if stop:
                        break
        result = tuple(paragraphs)
        self._opening_cache[path] = (version, result)
        return result

    def extract_transcript(self, path: Path, *, session_context: str = "") -> Detection:
        try:
            return extract_transcript(self.read_opening(path), Path(path), session_context=session_context)
        except (OSError, BadZipFile, KeyError, ET.ParseError, RuntimeError, ValueError) as exc:
            return Detection("transcript", "unavailable", reason=f"The transcript could not be read: {exc}", path=Path(path))

    def extract_row(self, table: SpeakerCSV, row: SpeakerRow) -> SpeakerProposal:
        """Stop on the first supported name; preserve prefilled and excluded rows."""
        values = row.values
        original = values[table.speaker_column]
        if not row.eligible:
            return SpeakerProposal(row.row_id, row.reference, original, "excluded")
        if row.has_speaker:
            return SpeakerProposal(row.row_id, row.reference, original, "preserved")
        attempts = []
        for extractor, column in ((self.extract_title, table.video_name_column), (self.extract_caption, table.caption_column)):
            result = extractor(values.get(column, ""))
            attempts.append(result)
            if result.status == "found":
                return SpeakerProposal(row.row_id, row.reference, original, "found", tuple(attempts))
        if self.transcripts is None:
            result = Detection("transcript", "unavailable", reason="No transcript folder was provided.")
        else:
            match = self.transcripts.lookup(row.reference)
            context = "\n".join(values.get(column, "") for column in (table.video_name_column, table.caption_column))
            result = self.extract_transcript(match.path, session_context=context) if match.path else Detection(
                "transcript", "unavailable", reason=match.message)
        attempts.append(result)
        status = "found" if result.status == "found" else "unresolved"
        return SpeakerProposal(row.row_id, row.reference, original, status, tuple(attempts))

    def extract_all(self, table: SpeakerCSV) -> tuple[SpeakerProposal, ...]:
        return tuple(self.extract_row(table, row) for row in table.rows)
