"""English local dashboard for public social-profile discovery."""

import streamlit as st

from finder.models import MatchStatus, Person, Platform, PlatformResult
from finder.export import SORT_OPTIONS, VISIBLE_COLUMNS, export_csv, result_rows, sort_rows
from finder.public_evidence import PublicEvidenceVerifier
from finder.query_builder import build_queries, manual_search_url
from finder.service import FinderService
from finder.speaker_workspace import render_speaker_workspace

st.set_page_config(page_title="Social Media Finder", page_icon="🔎", layout="wide")
st.markdown("""
<style>
.block-container { max-width: 1180px; padding-top: 2.5rem; }
h1 { letter-spacing: -0.045em; }
h2, h3 { letter-spacing: -0.02em; }
[data-testid="stForm"] { background: #fff; border-radius: 16px; }
</style>
""", unsafe_allow_html=True)


def render_result(result: PlatformResult, person: Person):
    with st.container(border=True):
        st.subheader(result.platform.value)
        if result.status == MatchStatus.LIKELY:
            st.success(result.status.value)
        elif result.status == MatchStatus.FAILED:
            st.error(result.status.value)
        elif result.status == MatchStatus.POSSIBLE:
            st.warning(result.status.value)
        else:
            st.info(result.status.value)
        if result.status == MatchStatus.NOT_SEARCHED:
            st.caption("Ready to search.")
        elif result.status == MatchStatus.NONE:
            st.write("The searches completed, but no candidate had enough supporting evidence.")
        elif result.status == MatchStatus.FAILED:
            st.write("A search request failed, so we cannot determine whether a reliable profile exists.")
        for index, candidate in enumerate(result.candidates):
            if index:
                st.divider()
            st.text(candidate.profile_name or "Profile name unavailable")
            if result.platform == Platform.LINKEDIN and candidate.job_title:
                st.caption(candidate.job_title)
            if result.platform == Platform.LINKEDIN and candidate.company:
                st.caption(candidate.company)
            st.caption(f"@{candidate.handle}")
            st.text(candidate.url)
            st.link_button("Open profile", candidate.url, use_container_width=True)
        with st.expander("Search queries & manual search"):
            runs = {run.query.text: run for run in result.runs if run.query.text}
            queries = [run.query for run in result.runs if run.query.text] or build_queries(person, result.platform)
            for query in queries:
                st.caption(query.stage)
                st.code(query.text, language=None, wrap_lines=True)
                run = runs.get(query.text)
                if run:
                    state = "Failed" if run.error else f"Completed · {len(run.hits)} indexed results"
                    st.caption(f"{state} · {run.attempts} attempt(s)")
                else:
                    st.caption("Not searched")
                st.link_button("Open manual search", manual_search_url(query.text))
        if result.errors or result.verification_notes:
            with st.expander("Technical details"):
                for run in result.runs:
                    if run.error:
                        st.text(f"{run.error.kind}: {run.error.detail}")
                for note in result.verification_notes:
                    st.text(note)


def preserve_search_form():
    keys = ("search_platforms", "search_full_name", "search_profession", "search_organization")
    if st.session_state.workspace == "Speakers Detection":
        saved = st.session_state.setdefault("social_form_values", {})
        saved.update({key: st.session_state[key] for key in keys if key in st.session_state})
    else:
        for key, value in st.session_state.get("social_form_values", {}).items():
            st.session_state[key] = value


st.title("Social Media Finder")
if st.session_state.get("workspace") == "Speakers":
    st.session_state.workspace = "Speakers Detection"
workspace = st.radio("Workspace", ["Speakers Detection", "Social search"], horizontal=True,
                     key="workspace", label_visibility="collapsed", on_change=preserve_search_form)
if workspace == "Speakers Detection":
    render_speaker_workspace()
    st.stop()
st.caption("Find public profiles on LinkedIn, Instagram, and X.")

st.session_state.setdefault("search_platforms", [platform.value for platform in Platform])
selected_platform_names = st.multiselect("Platforms", [platform.value for platform in Platform],
                                       key="search_platforms")
with st.form("person_search"):
    full_name = st.text_input("Full Name *", placeholder="e.g. Emma Watson", max_chars=160, key="search_full_name")
    profession = organization = ""
    if Platform.LINKEDIN.value in selected_platform_names:
        columns = st.columns(2)
        profession = columns[0].text_input("Profession / Occupation", placeholder="e.g. Actress", max_chars=160, key="search_profession")
        organization = columns[1].text_input("Company / Organization", placeholder="e.g. BBC", max_chars=160, key="search_organization")
        st.caption("Profession and company apply to LinkedIn only.")
    submitted = st.form_submit_button("Search", type="primary", use_container_width=True)

refresh = False
if "searched_person" in st.session_state:
    refresh = st.button("Refresh Search", help="Run fresh searches for the person shown below.")

person_to_search = None
if submitted:
    try:
        person_to_search = Person(full_name, profession, organization)
        if not selected_platform_names:
            raise ValueError("Select at least one platform.")
    except ValueError as exc:
        person_to_search = None
        st.error(str(exc))
elif refresh:
    previous = st.session_state.searched_person
    person_to_search = Person(previous.full_name, previous.profession, previous.organization)

if person_to_search:
    platforms_to_search = ([Platform(value) for value in selected_platform_names] if submitted
                           else list(st.session_state.get("searched_platforms", Platform)))
    st.session_state.searched_person = person_to_search
    st.session_state.searched_platforms = platforms_to_search
    st.session_state.results = {platform: PlatformResult(platform) for platform in platforms_to_search}
    if submitted or "list_platforms" not in st.session_state:
        st.session_state.list_platforms = [platform.value for platform in platforms_to_search]
    progress = st.progress(0, text="Preparing public web searches…")
    live_status = st.empty()
    live_results = st.empty()
    service = FinderService(verifier=PublicEvidenceVerifier(),
                            follower_cache=st.session_state.setdefault("follower_cache", {}))
    with st.spinner("Searching public indexes and checking available evidence…"):
        for index, result in enumerate(service.search_selected(person_to_search, platforms_to_search)):
            st.session_state.results[result.platform] = result
            live_status.info(" · ".join(
                f"{p.value}: {'Searching…' if st.session_state.results[p].status == MatchStatus.NOT_SEARCHED else 'Completed'}"
                for p in platforms_to_search
            ))
            completed = [item for item in st.session_state.results.values() if item.status != MatchStatus.NOT_SEARCHED]
            preview_columns = VISIBLE_COLUMNS if Platform.LINKEDIN in platforms_to_search else tuple(
                column for column in VISIBLE_COLUMNS if column not in {"Profession", "Company"})
            preview_rows = sort_rows(result_rows(person_to_search, completed))
            live_results.dataframe([{column: row[column] for column in preview_columns} for row in preview_rows],
                                   hide_index=True, use_container_width=True,
                                   column_config={"Reference URL": st.column_config.LinkColumn("Reference URL")})
            progress.progress((index + 1) / len(platforms_to_search), text=f"Completed {result.platform.value}")
    live_status.empty()
    progress.empty()
    # Display the refresh control consistently on the completed page.
    st.rerun()

if "searched_person" in st.session_state:
    person = st.session_state.searched_person
    results = st.session_state.results
    st.subheader("Search results")
    st.text(f"Results for {person.full_name}")
    context = [value for value in (person.profession, person.organization) if value]
    if context:
        st.caption(" · ".join(context))
    dates = [result.searched_at for result in results.values() if result.searched_at]
    if dates:
        st.caption(f"Last search: {max(dates)} · UTC")
    if "list_platforms" not in st.session_state:
        st.session_state.list_platforms = [platform.value for platform in results]
    controls = st.columns([2, 2, 1])
    visible_names = controls[0].multiselect(
        "Platforms in list", [platform.value for platform in results],
        key="list_platforms",
    )
    list_has_linkedin = Platform.LINKEDIN.value in visible_names
    sort_options = SORT_OPTIONS if list_has_linkedin else SORT_OPTIONS[:3]
    sort_by = controls[1].selectbox("Sort by", sort_options)
    view = controls[2].radio("View", ["List", "Profiles"], horizontal=True)
    visible_platforms = [Platform(value) for value in visible_names]
    visible_columns = VISIBLE_COLUMNS if list_has_linkedin else tuple(
        column for column in VISIBLE_COLUMNS if column not in {"Profession", "Company"})
    rows = sort_rows(result_rows(person, results.values(), visible_platforms), sort_by)
    if not visible_platforms:
        st.info("Select a platform to view or export results.")
    elif view == "List":
        for platform in visible_platforms:
            if results[platform].status == MatchStatus.FAILED:
                st.error(f"{platform.value}: search failed. Try Refresh Search.")
            elif results[platform].status == MatchStatus.NONE:
                st.info(f"{platform.value}: no matching profiles returned.")
        st.dataframe(
            [{column: row[column] for column in visible_columns} for row in rows],
            hide_index=True, use_container_width=True, column_order=visible_columns,
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                "Followers": st.column_config.NumberColumn(format="%d",
                    help="Numeric indexed count. Lookups may reuse an observation from this session for up to 24 hours; CSV includes its time and source."),
                "Reference URL": st.column_config.LinkColumn("Reference URL"),
            },
        )
        st.caption("Missing values are blank. Follower counts come from public indexes and may be rounded or outdated. Lookups can reuse a count from this session for up to 24 hours; CSV includes observation times.")
    else:
        for column, platform in zip(st.columns(len(visible_platforms)), visible_platforms):
            with column:
                render_result(results[platform], person)
    st.download_button("Download CSV", data=export_csv(rows), file_name="social-media-results.csv",
                       mime="text/csv", disabled=not bool(visible_platforms))
else:
    st.divider()
    initial_platforms = [Platform(value) for value in selected_platform_names]
    for column, platform in zip(st.columns(max(1, len(initial_platforms))), initial_platforms):
        with column:
            st.subheader(platform.value)
            st.caption("Not Searched")
    st.info("Enter a name to start. Add a profession or organization if the name is common.")
