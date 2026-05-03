# GCSE Study Tool

Streamlit study assistant for Maximos Rigas Psaltis's GCSE/IGCSE exam programme.

## What it does

- Shows the full exam schedule from the individual programme.
- Provides a separate module for each subject.
- Uploads PDFs and text files per subject.
- Builds a lightweight local search index over uploaded material.
- Saves extracted study materials to Supabase when configured, so materials can be reloaded after Streamlit redeploys.
- Uses retrieved material with Gemini to answer questions, generate practice and mark answers.
- Lets students choose a question from an uploaded past paper when extractable text is available.
- Exports generated practice as a PDF worksheet with questions and answer lines first, then model answers and mark schemes after a page break.
- Exports generated practice as a DOCX worksheet for editing.
- Logs revision sessions by subject.

## Subjects covered

- First Language English
- Literature in English
- Economics
- Biology
- Geography
- Physics
- Music
- Further Mathematics

Music includes Performing, Composing and Listening components.

## Local setup

```bash
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` from `.streamlit/secrets.example.toml` and add:

```toml
GEMINI_API_KEY = "your-key"
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

Run:

```bash
streamlit run app.py
```

## Deployment

For Streamlit Community Cloud, add `GEMINI_API_KEY` in the app secrets panel.
Add Supabase secrets there too if persistent saved materials are needed.
Do not commit `.streamlit/secrets.toml`.

## Supabase setup

Create this table in the Supabase SQL editor:

```sql
create table if not exists study_documents (
  id uuid primary key default gen_random_uuid(),
  student_id text not null default 'maximos',
  name text not null,
  subject text not null,
  document_type text not null,
  text text not null,
  created_at timestamptz not null default now(),
  unique (student_id, subject, document_type, name)
);
```

For Streamlit Cloud, use the project URL and service role key as secrets:

```toml
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

Keep the service role key only in Streamlit secrets. Do not commit it to GitHub.

## Notes

The first version uses local text extraction and keyword-based retrieval. Scanned
papers and image-only documents will need OCR or Gemini file upload support in a
later upgrade.
