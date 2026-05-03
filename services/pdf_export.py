from __future__ import annotations

import re
import textwrap
from io import BytesIO


def build_practice_pdf(subject: str, exam_label: str, practice_text: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError("reportlab is not installed.") from exc

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 54
    line_height = 14
    max_chars = 92

    questions = parse_practice_questions(practice_text)
    if not questions:
        questions = [
            {
                "title": "Question 1",
                "question": practice_text.strip(),
                "answer": "No model answer or mark scheme was separated from the generated text.",
            }
        ]

    def header(title: str) -> float:
        y = height - margin
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(margin, y, title)
        y -= 24
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margin, y, f"Subject: {subject}")
        y -= 14
        pdf.drawString(margin, y, f"Paper/component: {exam_label}")
        y -= 22
        return y

    y = header("GCSE Practice Worksheet")
    for item in questions:
        y = draw_wrapped(pdf, item["title"], margin, y, max_chars, line_height, bold=True)
        y = draw_wrapped(pdf, item["question"], margin, y, max_chars, line_height)
        y -= 8
        for _ in range(answer_line_count(item["question"])):
            if y < margin + 24:
                pdf.showPage()
                y = header("GCSE Practice Worksheet")
            pdf.line(margin, y, width - margin, y)
            y -= 18
        y -= 12
        if y < margin + 80:
            pdf.showPage()
            y = header("GCSE Practice Worksheet")

    pdf.showPage()
    y = header("Model Answers and Mark Schemes")
    for item in questions:
        y = draw_wrapped(pdf, item["title"], margin, y, max_chars, line_height, bold=True)
        y = draw_wrapped(pdf, item["answer"], margin, y, max_chars, line_height)
        y -= 10
        if y < margin + 80:
            pdf.showPage()
            y = header("Model Answers and Mark Schemes")

    pdf.save()
    return buffer.getvalue()


def parse_practice_questions(practice_text: str) -> list[dict[str, str]]:
    normalized_text = normalize_generated_text(practice_text)
    heading_pattern = re.compile(
        r"(?im)^\s*(?:[-–—]{3,}\s*)?(?:#{1,4}\s*)?(?:practice\s+)?(?:question|q)\s*(\d+)\s*[:.)-]?"
    )
    matches = list(heading_pattern.finditer(normalized_text))
    blocks: list[tuple[str, str]] = []

    if matches:
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized_text)
            blocks.append((f"Question {match.group(1)}", normalized_text[start:end].strip()))
    else:
        blocks.append(("Question 1", normalized_text.strip()))

    parsed = []
    for title, block in blocks:
        question_text = extract_between(
            block,
            start_labels=["Question:"],
            end_labels=["Model answer:", "Mark scheme points:", "Common mistake:"],
        )
        marks = extract_between(
            block,
            start_labels=["Marks available:"],
            end_labels=["Question:", "Model answer:", "Mark scheme points:", "Common mistake:"],
        )
        answer_text = extract_from_first_label(
            block,
            ["Model answer:", "Mark scheme points:", "Common mistake:"],
        )

        if not question_text:
            question_text = remove_answer_sections(block)
        if marks:
            question_text = f"Marks available: {marks}\n\n{question_text}"
        if not answer_text:
            answer_text = "No model answer or mark scheme was separated from the generated text."

        parsed.append(
            {
                "title": title,
                "question": clean_export_text(question_text),
                "answer": clean_export_text(answer_text),
            }
        )

    return parsed


def normalize_generated_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"(?m)^\s*[-–—]{3,}\s*$", "\n", text)
    text = re.sub(
        r"(?im)(?<!^)(?=\s*(?:#{1,4}\s*)?(?:practice\s+)?(?:question|q)\s*\d+\s*[:.)-]?)",
        "\n",
        text,
    )
    return text.strip()


def extract_between(block: str, start_labels: list[str], end_labels: list[str]) -> str:
    lower = block.lower()
    starts = [(lower.find(label.lower()), label) for label in start_labels]
    starts = [(pos, label) for pos, label in starts if pos >= 0]
    if not starts:
        return ""

    start_pos, label = min(starts)
    content_start = start_pos + len(label)
    end_positions = [
        lower.find(end_label.lower(), content_start)
        for end_label in end_labels
        if lower.find(end_label.lower(), content_start) >= 0
    ]
    content_end = min(end_positions) if end_positions else len(block)
    return block[content_start:content_end].strip()


def extract_from_first_label(block: str, labels: list[str]) -> str:
    lower = block.lower()
    starts = [lower.find(label.lower()) for label in labels if lower.find(label.lower()) >= 0]
    if not starts:
        return ""
    return block[min(starts) :].strip()


def remove_answer_sections(block: str) -> str:
    lower = block.lower()
    starts = [
        lower.find(label)
        for label in ["model answer:", "mark scheme points:", "common mistake:"]
        if lower.find(label) >= 0
    ]
    if starts:
        return block[: min(starts)].strip()
    return block.strip()


def clean_export_text(text: str) -> str:
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def answer_line_count(question_text: str) -> int:
    marks_match = re.search(r"Marks available:\s*(\d+)", question_text, re.IGNORECASE)
    if marks_match:
        return min(max(int(marks_match.group(1)) + 5, 8), 18)
    return 12


def draw_wrapped(
    pdf,
    text: str,
    x: float,
    y: float,
    max_chars: int,
    line_height: int,
    bold: bool = False,
) -> float:
    from reportlab.lib.pagesizes import A4

    _, height = A4
    margin = 54
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if not bold else 12)

    for paragraph in text.splitlines():
        if not paragraph.strip():
            y -= line_height
            continue
        for line in textwrap.wrap(paragraph, width=max_chars):
            if y < margin:
                pdf.showPage()
                y = height - margin
                pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if not bold else 12)
            pdf.drawString(x, y, line)
            y -= line_height
    return y - 6
