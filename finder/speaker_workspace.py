"""Compact Streamlit workspace for speaker review and completed-CSV download."""

import hashlib
from pathlib import Path

import streamlit as st

from finder.speaker_extract import SpeakerExtractor
from finder.speaker_import import SpeakerCSV, SpeakerImportError, TranscriptIndex, load_speaker_csv
from finder.speaker_review import SpeakerReview

SOURCE_LABELS = {"video_title": "High-res video name", "youtube_caption": "YouTube Caption", "transcript": "Transcript"}


def _forget_removed_upload():
    if st.session_state.get("speaker_csv") is None:
        state = st.session_state.get("speaker_workspace", {})
        for key in ("data", "filename", "token", "review", "editor_base", "extractor"):
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
    st.caption("Fill speakers for numbered talks, review names, and download your CSV.")
    uploaded = st.file_uploader("Content CSV", type=["csv"], key="speaker_csv", on_change=_forget_removed_upload)
    st.session_state.setdefault("speaker_folder", state.get("folder", ""))
    folder = st.text_input("Transcript folder", key="speaker_folder",
                           placeholder=r"e.g. C:\Content\TRANSCRIPTS V2",
                           help="Optional local folder on the machine running this app. Extract the ZIP first.")
    state["folder"] = folder
    options = ("Auto",) * 3
    state["options"] = options
    if uploaded is not None:
        state["data"] = uploaded.getvalue()
        state["filename"] = Path(uploaded.name).name
    if "data" not in state:
        st.info("Upload a CSV to start. Rows with numeric Ref Number values are processed.")
        return
    token = hashlib.sha256(state["data"] + repr(options).encode()).hexdigest()
    previous = state.get("review")
    if token != state.get("token") or not isinstance(previous.table if previous else None, SpeakerCSV):
        try:
            table = load_speaker_csv(state["data"])
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
    review = state["review"]
    if not isinstance(review, SpeakerReview):
        # Migrate state retained across a source-code reload without losing edits.
        review = SpeakerReview(review.table, dict(review.proposals), dict(review.edits), review.approved)
        state["review"] = review
        state["generation"] += 1
    st.caption(f"{state['filename']} · {len(review.table.eligible_rows)} numbered talks · "
               f"{len(review.table.rows)} total rows · {review.table.encoding}")
    if not review.table.eligible_rows:
        st.info("No eligible numbered talks found. Check Ref Number; duplicate references need to be resolved in the source CSV.")
        return
    actions = st.columns([1, 1, 3])
    find = actions[0].button("Find speakers", type="primary", key="find_speakers", use_container_width=True)
    reset = actions[1].button("Reset review", key="reset_speakers", use_container_width=True,
                              help="Discard manual edits and approval; keep the latest extraction suggestions.")
    st.subheader("Review speakers")
    st.caption("Edit or clear names, then apply reviewed changes to enable download. Existing values are kept by default.")
    if any(getattr(proposal.detection, "requires_review", False) for proposal in review.proposals.values()):
        st.caption("* = name mentioned in a transcript; may be a host or someone mentioned in passing. Remove * after checking.")
    generation = state["generation"]
    editor_key = f"speaker_editor_{generation}"
    # Freeze widget input while editing. Feeding edited data back into the same
    # editor resets its deltas and can lose alternating edits.
    if editor_key not in st.session_state:
        state["editor_base"] = review.editor_rows()
    state["editor_key"] = editor_key
    edited = st.data_editor(
        state["editor_base"], key=editor_key, hide_index=True, num_rows="fixed", use_container_width=True,
        column_order=["Ref Number", "High-res video name", "Speakers"],
        disabled=["_row_id", "Ref Number", "High-res video name"],
        column_config={"_row_id": None, "Speakers": st.column_config.TextColumn("Speakers", width="medium"),
                       "High-res video name": st.column_config.TextColumn(width="large")},
    )
    review.edit({row["_row_id"]: row["Speakers"] if row["Speakers"] is not None else "" for row in edited})
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
    if review.ready:
        st.caption("Review applied. The download contains every source row and column.")
    download = None
    if review.ready:
        try:
            download = review.export_csv()
        except UnicodeEncodeError:
            st.error(f"Some reviewed names cannot be saved as {review.table.encoding}. "
                     "Edit those names or upload a UTF-8 copy of the source CSV.")
    st.download_button("Download completed CSV", data=download if download is not None else b"",
                       file_name=f"{Path(state['filename']).stem}_speakers_filled.csv", mime="text/csv",
                       disabled=download is None, key="download_speakers")
