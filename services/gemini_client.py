from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeminiResult:
    text: str
    used_model: str


def get_api_key(st) -> str | None:
    try:
        key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        key = None
    return key or None


def generate_with_gemini(
    api_key: str,
    prompt: str,
    model: str = "gemini-2.0-flash",
) -> GeminiResult:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "The google-genai package is not installed. Install requirements.txt first."
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    text = getattr(response, "text", None) or "Gemini returned an empty response."
    return GeminiResult(text=text, used_model=model)


def build_subject_context(
    subject: str,
    board: str,
    level: str,
    component: str,
    retrieved_context: str,
) -> str:
    return f"""
Student: Maximos Rigas Psaltis, high-achieving GCSE/IGCSE student.
Subject: {subject}
Board: {board}
Level: {level}
Component or paper focus: {component}

Retrieved study material:
{retrieved_context}

Use the retrieved material where relevant. If the material is incomplete, say so
briefly and use general GCSE/IGCSE knowledge cautiously. Do not copy past-paper
questions verbatim; create fresh practice in the same style.
""".strip()
