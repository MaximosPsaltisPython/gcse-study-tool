from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import streamlit as st

from modules.subjects import profile_for
from services.document_loader import load_uploaded_documents
from services.docx_export import build_practice_docx
from services.gemini_client import build_subject_context, generate_with_gemini, get_api_key
from services.pdf_export import build_practice_pdf
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
    st.session_state.setdefault("latest_practice", "")
    st.session_state.setdefault("latest_practice_questions", [])
    st.session_state.setdefault("feedback_question", "")
    st.session_state.setdefault("feedback_answer", "")


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


def split_generated_questions(text: str) -> list[str]:
    pattern = re.compile(
        r"(?im)^\s*(?:#{1,4}\s*)?(?:practice\s+)?(?:question|q)\s*(\d+)\s*[:.)-]?\s*"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return [text.strip()] if text.strip() else []

    questions: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            questions.append(block)
    return questions


def clean_exam_text(text: str) -> str:
    noise_patterns = [
        r"DO NOT WRITE IN THIS AREA",
        r"Turn over",
        r"\*P\d+[A-Z]?\d*\*",
        r"\bPearson Edexcel\b",
        r"\bInternational GCSE\b",
        r"\bInstructions?\b.*",
        r"\bAnswer ALL questions\b",
        r"\bTotal Marks\b.*",
        r"\bQuestions? \d+.*",
    ]
    cleaned = text
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\.{8,}", "\n", cleaned)
    cleaned = re.sub(r"_{8,}", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_question_like_extract(text: str) -> bool:
    cleaned = clean_exam_text(text)
    words = cleaned.split()
    if len(words) < 18:
        return False

    title_only_patterns = [
        r"^\d{4}\s+SUMMER\b",
        r"^4[A-Z]{2}\d\s*-\s*\d[A-Z]?$",
        r"^Paper\s+\d",
        r"^Centre Number",
        r"^Candidate Number",
    ]
    if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in title_only_patterns):
        if len(words) < 45:
            return False

    question_signals = [
        r"\(\d+\)",  # marks such as (3)
        r"\bexplain\b",
        r"\bcalculate\b",
        r"\bdescribe\b",
        r"\bstate\b",
        r"\bdiagram\b",
        r"\bfigure\b",
        r"\btable\b",
        r"\bgraph\b",
        r"\bshow that\b",
        r"\bcomplete\b",
    ]
    return any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in question_signals)


def infer_year_from_filename(filename: str) -> str:
    match = re.search(r"(20\d{2})", filename)
    return match.group(1) if match else "Unknown year"


def split_past_paper_questions(text: str, filename: str) -> list[dict[str, str]]:
    page_pattern = re.compile(r"(?m)^\s*\[Page (\d+)\]\s*$")
    page_matches = list(page_pattern.finditer(text))
    year = infer_year_from_filename(filename)
    extracts: list[dict[str, str]] = []

    page_blocks: list[tuple[str, str]] = []
    for index, match in enumerate(page_matches):
        page = match.group(1)
        start = match.end()
        end = page_matches[index + 1].start() if index + 1 < len(page_matches) else len(text)
        page_blocks.append((page, text[start:end]))

    if not page_blocks:
        page_blocks = [("?", text)]

    question_pattern = re.compile(
        r"(?im)^\s*(?:question\s+|q\s*)?(\d{1,2})\s*(?:[.)]|\s{2,})"
    )

    for page, page_text in page_blocks:
        matches = list(question_pattern.finditer(page_text))
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(page_text)
            block = clean_exam_text(page_text[start:end])
            if is_question_like_extract(block):
                question_number = match.group(1)
                extracts.append(
                    {
                        "label": f"{year} - Page {page} - Question {question_number}",
                        "text": block,
                    }
                )

    if extracts:
        return extracts[:40]

    for page, page_text in page_blocks:
        block = clean_exam_text(page_text)
        if not is_question_like_extract(block):
            continue
        words = block.split()
        for index, start in enumerate(range(0, len(words), 220), start=1):
            fallback = " ".join(words[start : start + 220]).strip()
            if is_question_like_extract(fallback):
                extracts.append(
                    {
                        "label": f"{year} - Page {page} - Extract {index}",
                        "text": fallback,
                    }
                )
    return extracts[:20]


def clean_question_with_gemini(subject: str, exam, question: str) -> str:
    prompt = f"""
Clean this extracted GCSE/IGCSE past-paper question for a student answer box.

Subject: {subject}
Paper/component: {exam.component}
Board: {exam.board} {exam.level}

Rules:
- Remove page furniture such as "Turn over", "DO NOT WRITE IN THIS AREA", answer lines and candidate instructions.
- Preserve marks, subparts, numbers, units and formulas.
- If the question depends on a diagram, graph or table that is not present, add one line at the top: [Diagram/table needed].
- Do not answer the question.

Extracted text:
{question}
"""
    return run_gemini(prompt)


def old_split_past_paper_questions(text: str) -> list[str]:
    pattern = re.compile(
        r"(?im)^\s*(?:question\s+|q\s*)?(\d{1,2})\s*(?:[.)]|[a-z]\)|\s{2,})"
    )
    matches = list(pattern.finditer(text))
    questions: list[str] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if len(block.split()) >= 12:
            questions.append(block)

    if questions:
        return questions[:30]

    words = text.split()
    fallback: list[str] = []
    for start in range(0, len(words), 220):
        block = " ".join(words[start : start + 220]).strip()
        if block:
            fallback.append(block)
    return fallback[:12]


def filename_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or "practice"


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
Use this exact structure for each question:

Question 1
Marks available:
Question:
Model answer:
Mark scheme points:
Common mistake:

Question 2
Marks available:
Question:
Model answer:
Mark scheme points:
Common mistake:

Continue the same structure until all {count} questions are complete.
"""
        st.session_state.latest_practice = run_gemini(prompt)
        st.session_state.latest_practice_questions = split_generated_questions(
            st.session_state.latest_practice
        )

    if st.session_state.latest_practice:
        st.markdown(st.session_state.latest_practice)
        try:
            pdf_bytes = build_practice_pdf(
                subject,
                f"{exam.component} | {exam.board} {exam.level} {exam.unit_code}",
                st.session_state.latest_practice,
            )
            st.download_button(
                "Download practice worksheet as PDF",
                data=pdf_bytes,
                file_name=f"{filename_slug(subject)}-practice-worksheet.pdf",
                mime="application/pdf",
            )
        except RuntimeError as exc:
            st.warning(str(exc))
        try:
            docx_bytes = build_practice_docx(
                subject,
                f"{exam.component} | {exam.board} {exam.level} {exam.unit_code}",
                st.session_state.latest_practice,
            )
            st.download_button(
                "Download generated practice as DOCX",
                data=docx_bytes,
                file_name=f"{filename_slug(subject)}-practice.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except RuntimeError as exc:
            st.warning(str(exc))


def feedback_tab(subject: str, exam) -> None:
    st.subheader("Mark an answer")

    answer_source = st.radio(
        "Answer source",
        ["Uploaded past paper", "Generated practice", "Manual paste"],
        horizontal=True,
    )

    if answer_source == "Uploaded past paper":
        past_papers = [
            doc
            for doc in st.session_state.documents
            if doc.subject == subject and doc.document_type == "Past paper"
        ]
        if past_papers:
            paper_names = [doc.name for doc in past_papers]
            selected_paper_name = st.selectbox("Past paper", paper_names)
            selected_paper = past_papers[paper_names.index(selected_paper_name)]
            paper_questions = split_past_paper_questions(
                selected_paper.text,
                selected_paper.name,
            )

            if paper_questions:
                paper_question_labels = [question["label"] for question in paper_questions]
                selected_paper_question = st.selectbox("Question", paper_question_labels)
                paper_question_index = paper_question_labels.index(selected_paper_question)
                selected_extract = paper_questions[paper_question_index]["text"]
                with st.expander("Preview selected past-paper question", expanded=True):
                    st.write(selected_extract)
                action_cols = st.columns(2)
                with action_cols[0]:
                    if st.button("Use selected past-paper question"):
                        st.session_state.feedback_question = selected_extract
                with action_cols[1]:
                    if st.button("Clean selected question with Gemini"):
                        st.session_state.feedback_question = clean_question_with_gemini(
                            subject,
                            exam,
                            selected_extract,
                        )
            else:
                st.info("No extractable questions were found in this past paper.")
        else:
            st.info("Upload and index a past paper for this subject first.")

    elif answer_source == "Generated practice":
        if st.session_state.latest_practice_questions:
            question_labels = [
                f"Question {index + 1}"
                for index, _ in enumerate(st.session_state.latest_practice_questions)
            ]
            selected_question = st.selectbox("Generated question", question_labels)
            selected_index = question_labels.index(selected_question)
            selected_generated_question = st.session_state.latest_practice_questions[
                selected_index
            ]
            with st.expander("Preview selected generated question", expanded=True):
                st.markdown(selected_generated_question)
            if st.button("Use selected generated question"):
                st.session_state.feedback_question = selected_generated_question
        elif st.session_state.latest_practice:
            with st.expander("Preview latest generated practice", expanded=True):
                st.markdown(st.session_state.latest_practice)
            if st.button("Use latest generated practice as the question"):
                st.session_state.feedback_question = st.session_state.latest_practice
        else:
            st.info("Generate practice questions first, then return here.")

    else:
        st.caption("Paste or type any question below.")

    question = st.text_area("Question", height=260, key="feedback_question")
    answer = st.text_area("Maximos's answer", height=220, key="feedback_answer")

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
        st.write(f"**{item['date']}** - {item['minutes']} min - {item['confidence']} confidence")
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
