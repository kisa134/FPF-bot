"""FPF Studio — web UI for the reasoning orchestrator.

Run locally:
    pip install fastapi uvicorn
    uvicorn v1.web.server:app --reload
    open http://127.0.0.1:8000
"""

from .server import app

__all__ = ["app"]
