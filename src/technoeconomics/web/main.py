"""FastAPI application: the JSON API, plus the built Svelte frontend when present.

No gzip middleware: it buffers ``text/event-stream``, which would break the progress SSE.
Compression of the static assets and JSON is the reverse proxy's job (Caddy), which must also
be configured not to buffer the SSE endpoint.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from technoeconomics.web import api

# The Vite build output (``frontend/dist``): repo-relative in dev, overridable in the container.
_dist_env = os.environ.get("FRONTEND_DIST")
_DIST = (
    Path(_dist_env)
    if _dist_env
    else Path(__file__).resolve().parents[3] / "frontend" / "dist"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set up logging on startup; drain in-flight runs on shutdown."""
    logging.getLogger("technoeconomics").setLevel(logging.INFO)
    yield
    await api.manager.aclose_all()


app = FastAPI(
    lifespan=lifespan,
    redoc_url=None,
    docs_url="/api-docs",
    openapi_url="/api-docs/openapi.json",
)
app.include_router(api.router)

# Serve the built frontend when it exists; ``html=True`` falls back to index.html for client
# routes. Mounted last so it does not shadow ``/api``. Absent during API-only development and
# before the frontend scaffold lands (Step 2), so mounted conditionally.
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
