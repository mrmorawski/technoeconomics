"""FastAPI application: routes, per-session state, and preset wiring."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from technoeconomics.backend.preset import IndustrialHeat
from technoeconomics.web import sessions
from technoeconomics.web.forms import form_to_plant, plant_to_form

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Surface solve progress to the console at INFO, and run the solver task group.

    The task group (from `sessions.solver_pool`) owns every in-flight solve for the app's
    lifetime; we keep it on ``app.state`` so request handlers can submit solves into it. A
    solve can then outlive the handler that started it -- the SSE response streams after the
    handler returns.
    """
    for name in sessions.CAPTURED_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)
    async with sessions.solver_pool() as pool:
        app.state.solver_pool = pool
        yield


app = FastAPI(
    lifespan=lifespan,
    redoc_url=None,
    docs_url="/api-docs",
    openapi_url="/api-docs/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the landing page."""
    return templates.TemplateResponse(request, "index.jinja")


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """Render the about page."""
    return templates.TemplateResponse(request, "about.jinja")


@app.get("/docs", response_class=RedirectResponse)
async def docs(request: Request):
    """Redirect to the published documentation site."""
    return RedirectResponse(
        "https://mrmorawski.github.io/technoeconomics/getting-started/"
    )


@app.get("/industrial_heat", response_class=HTMLResponse)
async def industrial_heat(request: Request):
    """Render the model page, ensuring the visitor has a session to edit and solve.

    A first-time visitor has no ``sid`` cookie, so we mint a session holding a fresh
    default plant and set the cookie on the way out. A returning visitor's cookie points
    at their stored plant (with any edits from earlier solves), so the form reflects it.
    """
    preset = IndustrialHeat()
    session = sessions.get(request.cookies.get("sid"))
    new_sid = None
    if session is None:
        new_sid, session = sessions.create(preset.build())

    response = templates.TemplateResponse(
        request,
        "preset.jinja",
        {
            "title": preset.title,
            "description": preset.description,
            "schematic": preset.schematic_svg(),
            "components": plant_to_form(session.plant),
        },
    )
    if new_sid is not None:
        response.set_cookie("sid", new_sid, httponly=True, samesite="lax")
    return response


@app.post("/industrial_heat/init_solve", response_class=HTMLResponse)
async def industrial_heat_init_solve(request: Request):
    """Record the edited plant on the session; the page then opens the stream to solve it.

    No solve runs here -- this only overlays the submitted form onto the session's plant
    and returns the fragment that opens the EventSource. The solve is started by
    ``/stream_solve`` when the browser connects, so an unopened stream leaves no orphaned
    solve running.
    """
    session = sessions.get(request.cookies.get("sid"))
    if session is None:
        return templates.TemplateResponse(
            request, "_solving.jinja", {"error": "Session expired -- reload the page."}
        )
    form = await request.form()
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        session.plant = form_to_plant(session.plant, values)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "_solving.jinja", {"error": str(exc)}
        )
    return templates.TemplateResponse(request, "_solving.jinja", {})


@app.get("/industrial_heat/stream_solve", response_class=EventSourceResponse)
async def industrial_heat_stream_solve(
    request: Request,
) -> AsyncIterator[ServerSentEvent]:
    """Run the session's solve and stream it to the page as Server-Sent Events."""
    session = sessions.get(request.cookies.get("sid"))
    if session is None:
        yield ServerSentEvent(
            event="failed", raw_data="Session expired -- reload the page."
        )
        return
    preset = IndustrialHeat()
    async for kind, payload in sessions.stream_solve(
        session, preset, request.app.state.solver_pool
    ):
        match kind:
            case "log":
                yield ServerSentEvent(event="log", raw_data=str(payload))
            case "numbers":
                html = templates.get_template("_numbers.jinja").render(numbers=payload)
                yield ServerSentEvent(event="numbers", raw_data=html)
            case "chart":
                yield ServerSentEvent(event="chart", data=payload)
            case "error":
                yield ServerSentEvent(event="failed", raw_data=str(payload))
                return
            case "done":
                yield ServerSentEvent(event="done", raw_data="")
                return
