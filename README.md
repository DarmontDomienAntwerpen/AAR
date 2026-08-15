# Fire Service AAR Tool (v1)

Internal AI-assisted After Action Review tool for real fire-service
incidents. Commander DOCX reports and dispatch Excel data go in; an
interactive, evidence-traceable, chronological AAR comes out — reviewed and
finalised by a human facilitator, never by the AI alone.

- Product/engineering rationale and architecture: see [PROJECT_STATE.md](PROJECT_STATE.md).
- How to install, run, and test it: see [HANDOFF.md](HANDOFF.md).

Built with Python, Streamlit, SQLAlchemy/SQLite, and Pydantic. LLM access is
abstracted behind a provider interface (`aar/llm/`); the default and
test-suite provider is a deterministic mock — no API key required to run the
app or the tests. Uses Anthropic's Claude for the real-provider option.
