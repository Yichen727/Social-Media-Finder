"""English local dashboard for public social-profile discovery."""

import streamlit as st

from finder.models import MatchStatus, Person, Platform, PlatformResult
from finder.public_evidence import PublicEvidenceVerifier
from finder.query_builder import build_queries, manual_search_url
from finder.service import FinderService

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
        if result.partial:
            st.warning("Some queries failed. The available results may be incomplete.")
        if result.errors:
            for message in dict.fromkeys(error.message for error in result.errors):
                st.caption(message)
        for index, candidate in enumerate(result.candidates):
            if index:
                st.divider()
            st.text(candidate.profile_name or "Profile name unavailable")
            st.caption(f"@{candidate.handle} · {candidate.status.value} · Confidence: {candidate.confidence}")
            st.text(candidate.url)
            st.link_button("Open profile", candidate.url, use_container_width=True)
        with st.expander("Search queries & manual search"):
            runs = {run.query.text: run for run in result.runs}
            for query in build_queries(person, result.platform):
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


st.title("Social Media Finder")
st.caption("Find public profiles on LinkedIn, Instagram, and X.")

with st.form("person_search"):
    full_name = st.text_input("Full Name *", placeholder="e.g. Emma Watson", max_chars=160)
    columns = st.columns(3)
    profession = columns[0].text_input("Profession / Occupation", placeholder="e.g. Actress", max_chars=160)
    organization = columns[1].text_input("Organization / Affiliation", placeholder="e.g. BBC", max_chars=160)
    country = columns[2].text_input("Nationality / Country", placeholder="e.g. British", max_chars=160)
    st.caption("Only the name is required. Optional details help distinguish people with similar names.")
    submitted = st.form_submit_button("Search", type="primary", use_container_width=True)

refresh = False
if "searched_person" in st.session_state:
    refresh = st.button("Refresh Search", help="Run fresh searches for the person shown below.")

person_to_search = None
if submitted:
    try:
        person_to_search = Person(full_name, profession, organization, country)
    except ValueError as exc:
        st.error(str(exc))
elif refresh:
    person_to_search = st.session_state.searched_person

if person_to_search:
    st.session_state.searched_person = person_to_search
    st.session_state.results = {platform: PlatformResult(platform) for platform in Platform}
    progress = st.progress(0, text="Preparing public web searches…")
    live_status = st.empty()
    service = FinderService(verifier=PublicEvidenceVerifier())
    with st.spinner("Searching public indexes and checking available evidence…"):
        for index, platform in enumerate(Platform):
            live_status.info(" · ".join(
                f"{p.value}: {'Searching…' if p == platform else st.session_state.results[p].status.value}"
                for p in Platform
            ))
            st.session_state.results[platform] = service.search_platform(person_to_search, platform)
            progress.progress((index + 1) / len(Platform), text=f"Completed {platform.value}")
    live_status.empty()
    progress.empty()
    # Display the refresh control consistently on the completed page.
    st.rerun()

if "searched_person" in st.session_state:
    person = st.session_state.searched_person
    results = st.session_state.results
    st.subheader("Search results")
    st.text(f"Results for {person.full_name}")
    context = [value for value in (person.profession, person.organization, person.country) if value]
    if context:
        st.caption(" · ".join(context))
    dates = [result.searched_at for result in results.values() if result.searched_at]
    if dates:
        st.caption(f"Last search: {max(dates)} · UTC")
    for column, platform in zip(st.columns(3), Platform):
        with column:
            render_result(results[platform], person)
else:
    st.divider()
    for column, platform in zip(st.columns(3), Platform):
        with column:
            st.subheader(platform.value)
            st.caption("Not Searched")
    st.info("Enter a name to start. Add a profession, organization, or country if the name is common.")
