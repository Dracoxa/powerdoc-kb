# PowerDoc-KB

PowerDoc-KB is a lightweight web MVP for turning power electronics design documents into a traceable JSON knowledge base.

It accepts PDF, DOCX, TXT, and MD files, extracts text locally, then identifies:

- aerospace power-system topology schemes
- system sections such as orbit environment, bus regulation, solar array, battery, control equipment, reliability, and deliverables
- structured metrics and design constraints
- legacy debug views for parameters, formulas, components, and rule hits
- source snippets for traceability

The current extractor is a schema-driven local parser for aerospace power design documents. It is intentionally lightweight for Streamlit Cloud deployment. Heavier open-source document engines such as Docling, Unstructured, or Marker can be added later as optional backends for PDF layout analysis, OCR, and table reconstruction.

## Run

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal.

## Deploy On Streamlit Cloud

1. Push this folder to GitHub.
2. Open Streamlit Community Cloud and create a new app.
3. Select this repository.
4. Set the main file path to `app.py`.
5. Deploy.

If the app is already connected to this repository in Streamlit Cloud, pushing to `main` will usually trigger an automatic redeploy.

## Local Tests

```bash
python3 tests/run_extractor_tests.py
```

## Local Skill

This workspace also includes a local Codex skill at:

```text
.agents/skills/powerdoc-kb-extractor/SKILL.md
```

It documents the preferred extraction workflow for aerospace power-system knowledge-base building, including table-first parsing, topology relation extraction, schema grouping, and cleaner JSON output for the web UI.

## Notes

The current extractor is rule-based and schema-driven, so it can run without an API key. The JSON schema is designed so an LLM extraction stage can be added later without changing the frontend.
