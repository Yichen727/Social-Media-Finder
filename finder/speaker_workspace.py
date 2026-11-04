"""Compact Streamlit workspace for speaker review and CSV/XLSX download."""

import hashlib
from pathlib import Path

import streamlit as st

from finder.speaker_extract import SpeakerExtractor
from finder.speaker_excel import XLSX_MIME, SpeakerXLSX, load_speaker_xlsx, xlsx_sheet_names
from finder.speaker_import import SpeakerCSV, SpeakerImportError, TranscriptIndex, load_speaker_csv
from finder.speaker_review import SpeakerReview

SOURCE_LABELS = {"video_title": "High-res video name", "youtube_caption": "YouTube Caption", "transcript": "Transcript"}


def _visible_review_rows(review: SpeakerReview, need_review: bool) -> list[dict]:
    rows = review.editor_rows()
    if need_review:
        rows = [row for row in rows if not row["Speakers"].strip() or "*" in row["Speakers"]]
    return rows


def _forget_removed_upload():
    if st.session_state.get("speaker_csv") is None:
        state = st.session_state.get("speaker_workspace", {})
        for key in ("data", "filename", "token", "review", "editor_base", "extractor", "xlsx_token", "sheet_names", "worksheet_name"):
            state.pop(key, None)
        state["generation"] = state.get("generation", 0) + 1


def _evidence(review: SpeakerReview, generation: int):
    with st.expander("Source evidence"):
        rows = {row.row_id: row for row in review.table.eligible_rows}
        row_id = st.selectbox(
            "Talk", list(rows), key=f"speaker_evidence_{generation}",
            format_func=lambda key: f"{rows[key].values[review.table.reference_column]} · "
                                    f"{rows[key].values.get(review.table.video_name_column, '')}",
        )
        proposal = review.proposals.get(row_id)
        if row_id in review.edits:
            st.caption("Manually edited. Evidence below describes the original suggestion.")
        if not proposal:
            st.caption("Run Find speakers to see extraction evidence.")
        elif proposal.status == "preserved":
            st.caption("Existing CSV speaker value; preserved unless you edit it.")
        elif proposal.status == "found":
            found = proposal.detection
            st.caption(f"{SOURCE_LABELS[found.source]} · {found.name}")
            if found.path:
                st.caption(" · ".join(str(value) for value in
                                     (found.path.name, f"Paragraph {found.paragraph}", found.timestamp) if value))
            mentions = getattr(found, "mentions", ())
            if mentions:
                st.caption("* Transcript name candidates: review participation and spelling before using them.")
                groups = {}
                for mention in mentions:
                    key = (mention.paragraph, mention.timestamp, mention.evidence)
                    groups.setdefault(key, []).append(mention.name)
                for (paragraph, timestamp, excerpt), names in groups.items():
                    st.caption(f"{'; '.join(names)} · Paragraph {paragraph} {timestamp}")
                    st.text(excerpt)
            else:
                st.text(found.evidence)
        else:
            for attempt in proposal.attempts:
                st.caption(f"{SOURCE_LABELS[attempt.source]}: {attempt.reason}")


def render_speaker_workspace():
    state = st.session_state.setdefault("speaker_workspace", {})
    st.caption("Fill speakers for numbered talks, review names, and export CSV or XLSX.")
    uploaded = st.file_uploader("Content CSV or XLSX", type=["csv", "xlsx"], key="speaker_csv", on_change=_forget_removed_upload)
    st.session_state.setdefault("speaker_folder", state.get("folder", ""))
    folder = st.text_input("Transcript folder", key="speaker_folder",
                           placeholder=r"e.g. C:\Content\TRANSCRIPTS V2",
                           help="Optional local folder on the machine running this app. Extract the ZIP first.")
    state["folder"] = folder
    options = ("Auto",) * 3
    if uploaded is not None:
        state["data"] = uploaded.getvalue()
        state["filename"] = Path(uploaded.name).name
    if "data" not in state:
        st.info("Upload a CSV or XLSX to start.")
        return
    is_xlsx = Path(state["filename"]).suffix.lower() == ".xlsx"
    worksheet = None
    if is_xlsx:
        source_token = hashlib.sha256(state["data"]).hexdigest()
        try:
            if state.get("xlsx_token") != source_token:
                state["sheet_names"] = xlsx_sheet_names(state["data"])
                state["xlsx_token"] = source_token
            sheets = state["sheet_names"]
            if len(sheets) > 1:
                previous_sheet = state.get("worksheet_name")
                worksheet = st.selectbox(
                    "Worksheet", sheets, index=sheets.index(previous_sheet) if previous_sheet in sheets else 0,
                    key=f"speaker_worksheet_{source_token}", help="Changing the worksheet starts a new review.",
                )
            else:
                worksheet = sheets[0]
            state["worksheet_name"] = worksheet
            options = ("XLSX", worksheet)
        except SpeakerImportError as exc:
            st.error(str(exc))
            return
    token = hashlib.sha256(state["data"] + repr(options).encode()).hexdigest()
    previous = state.get("review")
    previous_token = state.get("token")
    previous_table = previous.table if previous else None
    if (token != previous_token or not isinstance(previous_table, SpeakerCSV)
            or is_xlsx and not isinstance(previous_table, SpeakerXLSX)):
        try:
            table = load_speaker_xlsx(state["data"], worksheet=worksheet) if is_xlsx else load_speaker_csv(state["data"])
        except SpeakerImportError as exc:
            st.error(str(exc))
            return
        state["review"] = SpeakerReview(table)
        if previous and token == state.get("token"):
            state["review"].proposals = dict(previous.proposals)
            state["review"].edits = dict(previous.edits)
            state["review"].approved = previous.approved
        state["token"] = token
        state["generation"] = state.get("generation", 0) + 1
        if not previous or token != previous_token:
            state["export_format"] = "XLSX" if is_xlsx else "CSV"
            st.session_state["speaker_export_format"] = state["export_format"]
    review = state["review"]
    if not isinstance(review, SpeakerReview):
        # Migrate state retained across a source-code reload without losing edits.
        review = SpeakerReview(review.table, dict(review.proposals), dict(review.edits), review.approved)
        state["review"] = review
        state["generation"] += 1
    source_label = f"XLSX · {review.table.worksheet_name}" if isinstance(review.table, SpeakerXLSX) else review.table.encoding
    st.caption(f"{state['filename']} · {len(review.table.eligible_rows)} numbered talks · "
               f"{len(review.table.rows)} total rows · {source_label}")
    if not review.table.eligible_rows:
        st.info("No eligible numbered talks found. Check Ref Number; duplicate references need to be resolved in the source table.")
        return
    actions = st.columns([1, 1, 3])
    find = actions[0].button("Find speakers", type="primary", key="find_speakers", use_container_width=True)
    reset = actions[1].button("Reset review", key="reset_speakers", use_container_width=True,
                              help="Discard manual edits and approval; keep the latest extraction suggestions.")
    st.subheader("Review speakers")
    st.caption("Edit or clear names, then apply reviewed changes to enable download. Existing values are kept by default.")
    if any(getattr(proposal.detection, "requires_review", False) for proposal in review.proposals.values()):
        st.caption("* = name mentioned in a transcript; may be a host or someone mentioned in passing. Remove * after checking.")
    st.session_state.setdefault("speaker_need_review", state.get("need_review_filter", False))
    need_review = st.checkbox("Need Review", key="speaker_need_review",
                              help="Show only blank Speakers cells or names containing *.")
    generation = state["generation"]
    editor_key = f"speaker_editor_{generation}"
    # Freeze widget input while editing. Feeding edited data back into the same
    # editor resets its deltas and can lose alternating edits.
    if editor_key not in st.session_state:
        state["editor_base"] = _visible_review_rows(review, state.get("need_review_filter", False))
    state["editor_key"] = editor_key
    if state["editor_base"]:
        edited = st.data_editor(
            state["editor_base"], key=editor_key, hide_index=True, num_rows="fixed", use_container_width=True,
            column_order=["Ref Number", "High-res video name", "Speakers"],
            disabled=["_row_id", "Ref Number", "High-res video name"],
            column_config={"_row_id": None, "Speakers": st.column_config.TextColumn("Speakers", width="medium"),
                           "High-res video name": st.column_config.TextColumn(width="large")},
        )
    else:
        edited = []
        st.info("No rows need review.")
    review.edit({row["_row_id"]: row["Speakers"] if row["Speakers"] is not None else "" for row in edited})
    # Apply the latest edits by source row ID before changing the visible set.
    visible_ids = [row["_row_id"] for row in _visible_review_rows(review, need_review)]
    refresh_filter = (need_review != state.get("need_review_filter", False)
                      or visible_ids != [row["_row_id"] for row in state["editor_base"]])
    # Consume the latest editor changes before rerunning extraction or resetting.
    if find:
        folder_path = folder.strip().strip('"')
        path = Path(folder_path).expanduser() if folder_path else None
        try:
            if path is not None and not path.is_dir():
                raise ValueError("Transcript folder is not accessible. Choose a local folder or leave it blank to use CSV sources only.")
            references = frozenset(row.reference for row in review.table.eligible_rows)
            extractor_key = (str(path.resolve()) if path else "", references)
            if state.get("extractor_key") != extractor_key or not isinstance(state.get("extractor"), SpeakerExtractor):
                state["extractor"] = SpeakerExtractor(TranscriptIndex(path, allowed_references=references) if path else None)
                state["extractor_key"] = extractor_key
            extractor = state["extractor"]
            if extractor.transcripts:
                extractor.transcripts.refresh()
            with st.spinner("Finding speakers…"):
                review.offer(extractor.extract_all(review.table))
            state["generation"] += 1
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(str(exc))
    if reset:
        review.reset()
        state["generation"] += 1
        st.rerun()
    _evidence(review, generation)
    if st.button("Apply reviewed changes", key="approve_speakers", disabled=review.ready):
        review.approve()
        st.rerun()
    st.session_state.setdefault("speaker_export_format", state.get("export_format", "XLSX" if is_xlsx else "CSV"))
    export_format = st.selectbox("Export format", ["CSV", "XLSX"], key="speaker_export_format")
    state["export_format"] = export_format
    if review.ready:
        st.caption("Review applied. The download contains every row and column from the reviewed table.")
    download = None
    if review.ready:
        try:
            download = review.export_xlsx() if export_format == "XLSX" else review.export_csv()
        except UnicodeEncodeError:
            st.error(f"Some reviewed names cannot be saved as {review.table.encoding}. "
                     "Edit those names or upload a UTF-8 copy of the source CSV.")
        except ValueError as exc:
            st.error(str(exc))
    st.download_button(f"Download completed {export_format}", data=download if download is not None else b"",
                       file_name=f"{Path(state['filename']).stem}_speakers_filled.{export_format.lower()}",
                       mime=XLSX_MIME if export_format == "XLSX" else "text/csv",
                       disabled=download is None, key="download_speakers")

    # Keep button actions above this refresh so a simultaneous cell edit cannot
    # swallow Find/Apply/Reset. Only the view changes; export uses the full table.
    if refresh_filter:
        state["need_review_filter"] = need_review
        state["generation"] += 1
        st.rerun()
