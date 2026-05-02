from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st

from modules.subjects import profile_for
from services.document_loader import LoadedDocument, load_uploaded_documents
from services.gemini_client import build_subject_context, generate_with_gemini, get_api_key
from services.rag_index import StudyIndex, format_context
from services.schedule import exams_for_subject, load_exams, subjects_from_exams, upcoming_exams


ROOT = Path(__file__).parent
SCHEDULE_PATH = ROOT / "data" / "exam_schedule.json"


st.set_page_config(
    page_title="GCSE Study Tool",
    page_icon="GCSE",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def cached_exams():
    return load_exams(SCHEDULE_PATH)


def init_state() -> None:
    st.session_state.setdefault("documents", [])
    st.session_state.setdefault("study_index", StudyIndex([]))
    st.session_state.setdefault("study_log", [])


def rebuild_index() -> None:
    st.session_state.study_index = StudyIndex.from_documents(st.session_state.documents)


def current_exam(subject: str):
    exams = exams_for_subject(cached_exams(), subject)
    future = [exam for exam in exams if exam.date and exam.date >= date.today()]
    return future[0] if future else (exams[0] if exams else None)


def selected_exam_options(subject: str) -> list[str]:
    exams = exams_for_subject(cached_exams(), subject)
    return [f"{exam.component} | {exam.board} {exam.level} {exam.unit_code}" for exam in exams]


def selected_exam_from_label(subject: str, label: str):
    exams = exams_for_subject(cached_exams(), subject)
    labels = selected_exam_options(subject)
    if label in labels:
        return exams[labels.index(label)]
    return current_exam(subject)


def show_exam_card(exam) -> None:
    if exam is None:
        st.info("No exam schedule is available for this subject yet.")
        return

    days_text = "unscheduled"
    if exam.days_until is not None:
        days_text = f"{exam.days_until} days"

    st.markdown(f"### {exam.subject}: {exam.component}")
    cols = st.columns(4)
    cols[0].metric("Date", exam.date_label)
    cols[1].metric("Countdown", days_text)
    cols[2].metric("Session", exam.session or "n/a")
    cols[3].metric("Extra time", f"{exam.extra_time_minutes} min" if exam.extra_time_minutes else "n/a")

    st.caption(
        " | ".join(
            part
            for part in [
                f"{exam.board} {exam.level}",
                f"Unit {exam.unit_code}",
                f"Paper {exam.paper_code}",
                f"Duration {exam.duration}" if exam.duration else None,
                f"Venue {exam.venue}" if exam.venue else None,
                f"Seat {exam.seat}" if exam.seat else None,
            ]
            if part
        )
    )


def retrieve_context(subject: str, query: str) -> tuple[str, list]:
    results = st.session_state.study_index.search(query, subject=subject, limit=6)
    return format_context(results), results


def run_gemini(prompt: str) -> str:
    api_key = get_api_key(st)
    if not api_key:
        return (
            "Gemini is not configured yet. Add GEMINI_API_KEY to .streamlit/secrets.toml "
            "locally, or to Streamlit Cloud secrets after deployment."
        )
    try:
        return generate_with_gemini(api_key, prompt).text
    except Exception as exc:
        return f"Gemini request failed: {exc}"


def dashboard_tab(exams) -> None:
    st.subheader("Upcoming papers")
    st.write("The schedule below is seeded from Maximos's individual exam programme.")

    for exam in upcoming_exams(exams, limit=10):
        with st.container(border=True):
            show_exam_card(exam)

    unscheduled = [exam for exam in exams if exam.date is None]
    with st.expander("Speaking, performing and composing components"):
        for exam in unscheduled:
            st.write(f"**{exam.subject} - {exam.component}**: {exam.board} {exam.level}, paper {exam.paper_code}, {exam.date_label}")


def subject_tab(subject: str, exam) -> None:
    profile = profile_for(subject)
    st.subheader(f"{subject} module")
    show_exam_card(exam)

    focus_cols = st.columns(2)
    with focus_cols[0]:
        st.markdown("#### Focus areas")
        for item in profile["focus"]:
            st.write(f"- {item}")
    with focus_cols[1]:
        st.markdown("#### Question styles")
        for item in profile["question_styles"]:
            st.write(f"- {item}")

    st.markdown("#### Upload and index material")
    doc_type = st.selectbox(
        "Material type",
        ["Past paper", "Mark scheme", "Syllabus/specification", "Class notes", "Model answer", "Other"],
        key=f"{subject}-doc-type",
    )
    uploads = st.file_uploader(
        "Upload PDFs or text files",
        type=["pdf", "txt", "md", "csv"],
        accept_multiple_files=True,
        key=f"{subject}-uploads",
    )

    if st.button("Add to study library", key=f"{subject}-add-docs"):
        new_docs = load_uploaded_documents(uploads, subject=subject, document_type=doc_type)
        st.session_state.documents.extend(new_docs)
        rebuild_index()
        st.success(f"Added {len(new_docs)} document(s) and rebuilt the index.")

    subject_docs = [doc for doc in st.session_state.documents if doc.subject == subject]
    st.caption(f"Indexed documents for this subject: {len(subject_docs)}")


def ask_tab(subject: str, exam) -> None:
    st.subheader("Ask my materials")
    question = st.text_area(
        "Question for the uploaded material",
        value=f"What should Maximos revise first for {subject}?",
        height=110,
    )

    if st.button("Search and answer with Gemini"):
        context, results = retrieve_context(subject, question)
        base = build_subject_context(subject, exam.board, exam.level, exam.component, context)
        prompt = f"{base}\n\nQuestion from parent/student:\n{question}\n\nAnswer clearly and cite the source filenames you used."
        st.session_state.last_answer = run_gemini(prompt)
        st.session_state.last_sources = results

    if st.session_state.get("last_answer"):
        st.markdown(st.session_state.last_answer)
        with st.expander("Retrieved source chunks"):
            for result in st.session_state.get("last_sources", []):
                st.write(f"**{result.chunk.source}** ({result.score:.2f})")
                st.write(result.chunk.text[:900])


def practice_tab(subject: str, exam) -> None:
    st.subheader("Generate practice")
    profile = profile_for(subject)
    question_style = st.selectbox("Question style", profile["question_styles"] or ["mixed practice"])
    topic = st.text_input("Topic focus", value=profile["focus"][0] if profile["focus"] else "")
    count = st.slider("Number of questions", 1, 10, 5)
    difficulty = st.select_slider("Difficulty", options=["Foundation", "Core", "Higher", "Grade 9 challenge"], value="Higher")

    if st.button("Generate practice questions"):
        query = f"{subject} {exam.component} {topic} {question_style} mark scheme"
        context, _ = retrieve_context(subject, query)
        base = build_subject_context(subject, exam.board, exam.level, exam.component, context)
        prompt = f"""
{base}

Create {count} fresh GCSE/IGCSE practice questions.
Style: {question_style}
Topic: {topic}
Difficulty: {difficulty}

For each question include:
1. Marks available
2. Question
3. Model answer
4. Mark scheme points
5. One common mistake
"""
        st.markdown(run_gemini(prompt))


def feedback_tab(subject: str, exam) -> None:
    st.subheader("Mark an answer")
    question = st.text_area("Question", height=120)
    answer = st.text_area("Maximos's answer", height=180)

    if st.button("Get feedback"):
        query = f"{subject} {exam.component} mark scheme {question}"
        context, _ = retrieve_context(subject, query)
        base = build_subject_context(subject, exam.board, exam.level, exam.component, context)
        prompt = f"""
{base}

Mark this answer using the retrieved material and GCSE/IGCSE expectations.

Question:
{question}

Student answer:
{answer}

Return:
1. Estimated mark and why
2. What is correct
3. Missing or weak points
4. How to improve
5. A concise model answer
6. Two follow-up questions
"""
        st.markdown(run_gemini(prompt))


def progress_tab(subject: str) -> None:
    st.subheader("Revision log")
    with st.form("study-log-form"):
        minutes = st.number_input("Minutes studied", min_value=5, max_value=240, value=25, step=5)
        confidence = st.selectbox("Confidence after session", ["Low", "Medium", "High"])
        notes = st.text_area("Notes", placeholder="What improved? What needs another pass?")
        submitted = st.form_submit_button("Log session")

    if submitted:
        st.session_state.study_log.insert(
            0,
            {
                "date": date.today().isoformat(),
                "subject": subject,
                "minutes": int(minutes),
                "confidence": confidence,
                "notes": notes or "No notes added.",
            },
        )
        st.success("Session logged.")

    subject_log = [item for item in st.session_state.study_log if item["subject"] == subject]
    total_minutes = sum(item["minutes"] for item in subject_log)
    st.metric("Logged minutes for this subject", total_minutes)
    for item in subject_log[:8]:
        st.write(f"**{item['date']}** · {item['minutes']} min · {item['confidence']} confidence")
        st.caption(item["notes"])


def export_tab() -> None:
    st.subheader("Export")
    export_payload = {
        "documents": [
            {
                "name": doc.name,
                "subject": doc.subject,
                "document_type": doc.document_type,
                "characters": len(doc.text),
            }
            for doc in st.session_state.documents
        ],
        "study_log": st.session_state.study_log,
    }
    st.download_button(
        "Download study data",
        data=json.dumps(export_payload, indent=2),
        file_name="maximos-gcse-study-data.json",
        mime="application/json",
    )


def main() -> None:
    init_state()
    exams = cached_exams()
    subjects = subjects_from_exams(exams)

    st.title("GCSE Study Tool")
    st.write("A subject-by-subject study assistant for Maximos's exam programme.")

    with st.sidebar:
        st.header("Study module")
        subject = st.selectbox("Subject", subjects)
        exam_labels = selected_exam_options(subject)
        exam_label = st.selectbox("Paper/component", exam_labels)
        exam = selected_exam_from_label(subject, exam_label)
        st.divider()
        st.metric("Indexed documents", len(st.session_state.documents))
        st.metric("Index chunks", len(st.session_state.study_index.chunks))
        st.caption("Gemini key is read from Streamlit secrets.")

    tabs = st.tabs(
        [
            "Dashboard",
            "Subject module",
            "Ask materials",
            "Practice",
            "Feedback",
            "Progress",
            "Export",
        ]
    )

    with tabs[0]:
        dashboard_tab(exams)
    with tabs[1]:
        subject_tab(subject, exam)
    with tabs[2]:
        ask_tab(subject, exam)
    with tabs[3]:
        practice_tab(subject, exam)
    with tabs[4]:
        feedback_tab(subject, exam)
    with tabs[5]:
        progress_tab(subject)
    with tabs[6]:
        export_tab()


if __name__ == "__main__":
    main()
