# GCSE Study Tool

Streamlit study assistant for Maximos Rigas Psaltis's GCSE/IGCSE exam programme.

## What it does

- Shows the full exam schedule from the individual programme.
- Provides a separate module for each subject.
- Uploads PDFs and text files per subject.
- Builds a lightweight local search index over uploaded material.
- Uses retrieved material with Gemini to answer questions, generate practice and mark answers.
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
```

Run:

```bash
streamlit run app.py
```

## Deployment

For Streamlit Community Cloud, add `GEMINI_API_KEY` in the app secrets panel.
Do not commit `.streamlit/secrets.toml`.

## Notes

The first version uses local text extraction and keyword-based retrieval. Scanned
papers and image-only documents will need OCR or Gemini file upload support in a
later upgrade.
