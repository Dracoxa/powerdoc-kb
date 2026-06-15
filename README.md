# PowerDoc-KB

PowerDoc-KB is a lightweight web MVP for turning power electronics design documents into a traceable JSON knowledge base.

It accepts PDF, DOCX, TXT, and MD files, extracts text locally, then identifies:

- power topologies
- electrical parameters
- design formulas
- components
- layout, EMI, thermal, protection, and troubleshooting rules
- source snippets for traceability

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

## Notes

The current extractor is rule-based, so it can run without an API key. The JSON schema is designed so an LLM extraction stage can be added later without changing the frontend.
