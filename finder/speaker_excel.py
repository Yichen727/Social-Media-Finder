"""Read XLSX tables and update approved speaker cells without rewriting the workbook."""
from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from datetime import date, datetime, time
import io
import posixpath
import re
from xml.dom import minidom
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from finder.speaker_import import SpeakerCSV, SpeakerImportError, load_speaker_csv

SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class SpeakerXLSX(SpeakerCSV):
    workbook_bytes: bytes = b""
    worksheet_name: str = ""
    worksheet_path: str = ""
    source_column_count: int = 0


def _sheet_paths(data: bytes) -> dict[str, str]:
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                item.get("Id"): item.get("Target", "") for item in relationships
                if item.get("Type", "").endswith("/worksheet") and item.get("TargetMode") != "External"
            }
            result = {}
            for sheet in workbook.findall(f"{{{SHEET_NS}}}sheets/{{{SHEET_NS}}}sheet"):
                target = targets.get(sheet.get(f"{{{REL_NS}}}id"))
                if not target or sheet.get("state", "visible") != "visible":
                    continue
                path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
                if path.startswith("xl/") and path in archive.namelist():
                    result[sheet.get("name", "")] = path
            if not result:
                raise SpeakerImportError("The XLSX workbook has no visible worksheets.")
            return result
    except (BadZipFile, KeyError, ET.ParseError, OSError) as exc:
        raise SpeakerImportError("The file is not a readable XLSX workbook. Save it as .xlsx in Excel and try again.") from exc


def xlsx_sheet_names(data: bytes) -> tuple[str, ...]:
    return tuple(_sheet_paths(data))


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise SpeakerImportError("Excel support requires openpyxl. Restart using run.bat or run.command to install the updated requirements.") from exc
    return openpyxl


def _cell_text(cell, cached, *, required: bool = False) -> str:
    value = cell.value
    if cell.data_type == "f":
        cached_empty_string = cached.value is None and cached.data_type == "str"
        if cached.value is None and not cached_empty_string and required:
            raise SpeakerImportError(f"Cell {cell.coordinate} has a formula without a saved result. Open and save the workbook in Excel or LibreOffice before importing it.")
        value = "" if cached_empty_string else cached.value if cached.value is not None else cell.value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, int) or value.is_integer():
            integer = int(value)
            if integer >= 0 and re.fullmatch(r"0+", cell.number_format or ""):
                return str(integer).zfill(len(cell.number_format))
            return str(integer)
    return str(value)


def load_speaker_xlsx(data: bytes, *, worksheet: str | None = None) -> SpeakerXLSX:
    paths = _sheet_paths(data)
    worksheet = worksheet if worksheet is not None else next(iter(paths))
    if worksheet not in paths:
        raise SpeakerImportError("Choose a visible worksheet from this workbook.")
    excel = _openpyxl()
    book = cached_book = None
    try:
        # Bound the imported table by actual cell contents, not distant formatting.
        with ZipFile(io.BytesIO(data)) as archive:
            root = ET.fromstring(archive.read(paths[worksheet]))
        coordinates = [excel.utils.cell.coordinate_to_tuple(cell.get("r"))
                       for cell in root.iter(f"{{{SHEET_NS}}}c")
                       if cell.find(f"{{{SHEET_NS}}}f") is not None
                       or any(node.text is not None for node in cell.iter()
                              if node.tag in {f"{{{SHEET_NS}}}v", f"{{{SHEET_NS}}}t"})]
        if not coordinates:
            raise SpeakerImportError("The selected worksheet is empty.")
        last_row = max(row for row, _ in coordinates)
        width = max(column for _, column in coordinates)
        book = excel.load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        cached_book = excel.load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
        source_rows = book[worksheet].iter_rows(max_row=last_row, max_col=width)
        cached_rows = cached_book[worksheet].iter_rows(max_row=last_row, max_col=width)
        header_cells = next(source_rows)
        header_cache = next(cached_rows)
        headers = [_cell_text(cell, cached, required=True) for cell, cached in zip(header_cells, header_cache)]
        source_names = {"ref number", "high-res video name", "youtube caption", "speaker", "speakers"}
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        for row, cached in zip(source_rows, cached_rows):
            writer.writerow([_cell_text(cell, saved, required=" ".join(header.split()).casefold() in source_names)
                             for header, cell, saved in zip(headers, row, cached)])
        table = load_speaker_csv(output.getvalue().encode("utf-8-sig"))
        speaker_column = table.headers.index(table.speaker_column) + 1
        for merged in root.findall(f"{{{SHEET_NS}}}mergeCells/{{{SHEET_NS}}}mergeCell"):
            first_col, _, last_col, last_merged_row = excel.utils.cell.range_boundaries(merged.get("ref"))
            if first_col <= speaker_column <= last_col and last_merged_row >= 2:
                raise SpeakerImportError("The Speakers column contains merged cells. Unmerge those cells in Excel before importing.")
        return SpeakerXLSX(**{field.name: getattr(table, field.name) for field in fields(SpeakerCSV)},
                           workbook_bytes=data, worksheet_name=worksheet,
                           worksheet_path=paths[worksheet], source_column_count=width)
    except SpeakerImportError:
        raise
    except (BadZipFile, KeyError, ET.ParseError, OSError, ValueError, TypeError) as exc:
        raise SpeakerImportError(f"The XLSX worksheet could not be read: {exc}") from exc
    finally:
        if book is not None:
            book.close()
        if cached_book is not None:
            cached_book.close()


def _validate_text(text: str):
    if len(text) > 32767 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        raise SpeakerImportError("A cell contains text Excel cannot store. Shorten it to 32,767 characters or remove control characters before exporting XLSX.")


def _elements(node, name: str):
    return [child for child in node.childNodes if child.nodeType == child.ELEMENT_NODE and child.localName == name]


def _element(document, root, name: str):
    return document.createElementNS(root.namespaceURI, f"{root.prefix}:{name}" if root.prefix else name)


def _xml_bytes(document) -> bytes:
    # Preserve carriage returns represented as character references in cell text.
    return document.toxml(encoding="utf-8").replace(b"\r", b"&#13;")


def _update_workbook(table: SpeakerXLSX, approved: dict[int, str]) -> bytes:
    excel = _openpyxl()
    column = table.headers.index(table.speaker_column) + 1
    edits = {row.row_id + 2: approved[row.row_id] for row in table.eligible_rows
             if approved[row.row_id] != row.values[table.speaker_column]}
    if column > table.source_column_count:
        edits[1] = table.speaker_column
    if not edits:
        return table.workbook_bytes
    with ZipFile(io.BytesIO(table.workbook_bytes)) as original:
        document = minidom.parseString(original.read(table.worksheet_path))
        root = document.documentElement
        sheet_data = _elements(root, "sheetData")[0]
        rows = {int(row.getAttribute("r")): row for row in _elements(sheet_data, "row")}
        replaced_formula = False
        for number, value in sorted(edits.items()):
            _validate_text(value)
            row = rows.get(number)
            if row is None:
                row = _element(document, root, "row")
                row.setAttribute("r", str(number))
                following = next((item for item in _elements(sheet_data, "row") if int(item.getAttribute("r")) > number), None)
                sheet_data.insertBefore(row, following)
                rows[number] = row
            coordinate = f"{excel.utils.get_column_letter(column)}{number}"
            cell = next((item for item in _elements(row, "c") if item.getAttribute("r") == coordinate), None)
            if cell is None:
                cell = _element(document, root, "c")
                cell.setAttribute("r", coordinate)
                following = next((item for item in _elements(row, "c")
                                  if excel.utils.cell.coordinate_to_tuple(item.getAttribute("r"))[1] > column), None)
                if following is None:
                    following = next(iter(_elements(row, "extLst")), None)
                row.insertBefore(cell, following)
            for child in list(cell.childNodes):
                if child.nodeType == child.ELEMENT_NODE and child.localName in {"f", "v", "is"}:
                    replaced_formula |= child.localName == "f"
                    cell.removeChild(child)
            cell.setAttribute("t", "inlineStr")
            inline = _element(document, root, "is")
            text = _element(document, root, "t")
            text.setAttributeNS("http://www.w3.org/XML/1998/namespace", "xml:space", "preserve")
            text.appendChild(document.createTextNode(value))
            inline.appendChild(text)
            cell.insertBefore(inline, next(iter(_elements(cell, "extLst")), None))
        dimensions = _elements(root, "dimension")
        if dimensions and column > table.source_column_count:
            _, _, last_col, last_row = excel.utils.cell.range_boundaries(dimensions[0].getAttribute("ref"))
            dimensions[0].setAttribute("ref", f"A1:{excel.utils.get_column_letter(max(column, last_col))}{last_row}")
        updates = {table.worksheet_path: _xml_bytes(document)}
        # Ask Excel to refresh dependent formula values after a speaker edit.
        workbook = minidom.parseString(original.read("xl/workbook.xml"))
        workbook_root = workbook.documentElement
        calculation = next(iter(_elements(workbook_root, "calcPr")), None)
        if calculation is None:
            calculation = _element(workbook, workbook_root, "calcPr")
            successors = {"oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr", "smartTagTypes", "webPublishing", "fileRecoveryPr", "webPublishObjects", "extLst"}
            following = next((node for node in workbook_root.childNodes
                              if node.nodeType == node.ELEMENT_NODE and node.localName in successors), None)
            workbook_root.insertBefore(calculation, following)
        calculation.setAttribute("fullCalcOnLoad", "1")
        calculation.setAttribute("forceFullCalc", "1")
        updates["xl/workbook.xml"] = _xml_bytes(workbook)
        skip = set()
        if replaced_formula and "xl/calcChain.xml" in original.namelist():
            skip.add("xl/calcChain.xml")
            for filename, element, attribute, suffix in (
                ("xl/_rels/workbook.xml.rels", "Relationship", "Type", "/calcChain"),
                ("[Content_Types].xml", "Override", "PartName", "/xl/calcChain.xml"),
            ):
                metadata = minidom.parseString(original.read(filename))
                for item in _elements(metadata.documentElement, element):
                    if item.getAttribute(attribute).endswith(suffix):
                        item.parentNode.removeChild(item)
                updates[filename] = _xml_bytes(metadata)
        output = io.BytesIO()
        with ZipFile(output, "w") as target:
            target.comment = original.comment
            for info in original.infolist():
                if info.filename not in skip:
                    target.writestr(info, updates.get(info.filename, original.read(info.filename)))
        return output.getvalue()


def export_speaker_xlsx(table: SpeakerCSV, approved: dict[int, str]) -> bytes:
    if isinstance(table, SpeakerXLSX):
        return _update_workbook(table, approved)
    excel = _openpyxl()
    workbook = excel.Workbook()
    sheet = workbook.active
    sheet.title = "Speakers"
    speaker_index = table.headers.index(table.speaker_column)
    records = [table.headers]
    for row in table.rows:
        cells = list(row.cells)
        if row.eligible:
            cells[speaker_index] = approved[row.row_id]
        records.append(cells)
    for row_number, row in enumerate(records, 1):
        for column, value in enumerate(row, 1):
            _validate_text(value)
            cell = sheet.cell(row_number, column, value)
            cell.data_type = "s"  # CSV values remain literal text, including '=...'.
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
