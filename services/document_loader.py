from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable


@dataclass(frozen=True)
class LoadedDocument:
    name: str
    subject: str
    document_type: str
    text: str


def load_uploaded_documents(
    uploaded_files: Iterable,
    subject: str,
    document_type: str,
) -> list[LoadedDocument]:
    documents: list[LoadedDocument] = []

    for file in uploaded_files:
        text = extract_text(file)
        if text.strip():
            documents.append(
                LoadedDocument(
                    name=file.name,
                    subject=subject,
                    document_type=document_type,
                    text=text,
                )
            )

    return documents


def extract_text(file) -> str:
    name = file.name.lower()

    if name.endswith(".pdf"):
        return extract_pdf_text(file)

    if name.endswith((".txt", ".md", ".csv")):
        return file.getvalue().decode("utf-8", errors="ignore")

    return (
        f"[{file.name}] was uploaded, but text extraction is not available for "
        "this file type yet. Use Gemini's direct file upload in a later version "
        "for image-only or scanned materials."
    )


def extract_pdf_text(file) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "pypdf is not installed, so PDF text could not be extracted."

    reader = PdfReader(BytesIO(file.getvalue()))
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {page_number}]\n{text}")

    if not pages:
        return (
            f"{file.name} did not contain extractable text. It may be scanned; "
            "OCR can be added as the next upgrade."
        )

    return "\n\n".join(pages)
