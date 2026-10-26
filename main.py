"""Entry point kompatibel untuk platform deploy (bind 0.0.0.0)."""

from __future__ import annotations

import os

from app.main import app

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("SIDEWA_PORT", "8000")))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True)
