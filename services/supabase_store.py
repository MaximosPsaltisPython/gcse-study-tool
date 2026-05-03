from __future__ import annotations

from services.document_loader import LoadedDocument


TABLE_NAME = "study_documents"


def is_configured(st) -> bool:
    return bool(_secret(st, "SUPABASE_URL") and _supabase_key(st))


def load_documents(st, subject: str) -> list[LoadedDocument]:
    client = _client(st)
    response = (
        client.table(TABLE_NAME)
        .select("name, subject, document_type, text")
        .eq("student_id", "maximos")
        .eq("subject", subject)
        .execute()
    )
    return [
        LoadedDocument(
            name=item["name"],
            subject=item["subject"],
            document_type=item["document_type"],
            text=item["text"],
        )
        for item in response.data or []
    ]


def save_documents(st, documents: list[LoadedDocument]) -> int:
    if not documents:
        return 0

    client = _client(st)
    saved = 0
    for document in documents:
        client.table(TABLE_NAME).upsert(
            {
                "student_id": "maximos",
                "name": document.name,
                "subject": document.subject,
                "document_type": document.document_type,
                "text": document.text,
            },
            on_conflict="student_id,subject,document_type,name",
        ).execute()
        saved += 1
    return saved


def delete_subject_documents(st, subject: str) -> None:
    (
        _client(st)
        .table(TABLE_NAME)
        .delete()
        .eq("student_id", "maximos")
        .eq("subject", subject)
        .execute()
    )


def _client(st):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("The supabase package is not installed.") from exc

    url = _secret(st, "SUPABASE_URL")
    key = _supabase_key(st)
    if not url or not key:
        raise RuntimeError("Supabase is not configured in Streamlit secrets.")
    return create_client(url, key)


def _supabase_key(st) -> str | None:
    return _secret(st, "SUPABASE_SERVICE_ROLE_KEY") or _secret(st, "SUPABASE_ANON_KEY")


def _secret(st, name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None
