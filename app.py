"""Default entry point for platforms that run `python app.py`."""

from __future__ import annotations

import os

import uvicorn

from app.main import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("SIDEWA_PORT", "8000")))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True)
else:
    # Expose ASGI app for servers that import `app:app`.
    application = app
