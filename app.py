"""Entrypoint for the Fire Service AAR Tool.

Run with: uvicorn app:app
(or: python app.py, for a plain `python app.py` dev-run convenience)
"""
from aar.web.app import app  # noqa: F401 — re-exported as the `app:app` ASGI target

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
