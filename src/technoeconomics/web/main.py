"""FastAPI application: the JSON API, plus the built Svelte frontend when served from here.

No gzip middleware: it buffers ``text/event-stream``, which would break the progress SSE.
Compression of the static assets and JSON is the reverse proxy's job (Caddy), which must also
be configured not to buffer the SSE endpoint.

The frontend is a **separate build artifact**, not part of this Python package: the wheel
contains no static files and this module never reaches outside its own distribution to find
any. In production the container builds ``frontend/dist`` in its own stage and points
``FRONTEND_DIST`` at it. In development the Vite dev server serves the frontend and proxies
``/api`` here (see ``frontend/vite.config.ts``), so the variable is unset and nothing is
mounted. If it *is* set and does not name a directory, `StaticFiles` raises at startup --
a mis-built image should fail loudly, not boot and serve 404s.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from technoeconomics.web import api

_DIST = os.environ.get("FRONTEND_DIST")


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


@app.exception_handler(RequestValidationError)
async def _request_validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Reshape FastAPI's 422 body into the API's own path-addressed error shape.

    FastAPI answers a malformed request with ``{"detail": [...]}`` while the API's own
    validation answers with ``{"errors": [{"path", "message"}]}``. Two shapes behind one status
    code is how a client ends up parsing the wrong one and reporting nothing at all, so the
    request-validation errors are reshaped to match the declared contract.

    The path is the last location segment, which for the overlay and enabled maps is the spec
    path or component id the client already addresses fields by.
    """
    errors = [
        {
            "path": str(e["loc"][-1]) if len(e["loc"]) > 1 else "",
            "message": e["msg"],
        }
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"errors": errors})


app.include_router(api.router)

# Serve the built frontend when this process is the one serving it. Mounted last and at "/",
# so it is matched only after the API routes and the docs.
if _DIST:
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
