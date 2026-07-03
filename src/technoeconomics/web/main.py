"""FastAPI application: routes, per-session state, and preset wiring."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from technoeconomics.backend.preset import IndustrialHeat
from technoeconomics.web import share
from technoeconomics.web.forms import form_to_plant, plant_to_form
from technoeconomics.web.session import SessionManager

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")
sessions = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Logging, clearly terminate sessions."""
    logging.getLogger("technoeconomics").setLevel(logging.INFO)
    yield
    await sessions.aclose_all()


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
    token = request.query_params.get("p")

    # build shared network if present
    if token is not None:
        try:
            plant = share.decode(token)
        except ValueError:
            plant = None
        if plant is not None:
            new_sid, _ = sessions.create(plant)
            redirect = RedirectResponse(
                request.url_for("industrial_heat"), status_code=303
            )
            redirect.set_cookie("sid", new_sid, httponly=True, samesite="lax")
            return redirect

    cookie_sid = request.cookies.get("sid")
    sid, session = sessions.get_or_create(cookie_sid, preset.build)
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
    if sid != cookie_sid:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.post("/industrial_heat/reset", response_class=HTMLResponse)
async def industrial_heat_reset(request: Request):
    """Reset the session's plant to the preset defaults and re-render the form.

    htmx swaps the returned form fragment in place of the current one. If the session has
    expired, a fresh one is minted (and its cookie set) so reset still yields a usable form.
    """
    cookie_sid = request.cookies.get("sid")
    sid, session = sessions.get_or_create(cookie_sid, IndustrialHeat().build)
    session.plant = IndustrialHeat().build()
    response = templates.TemplateResponse(
        request, "_form.jinja", {"components": plant_to_form(session.plant)}
    )
    if sid != cookie_sid:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.post("/industrial_heat/share", response_class=HTMLResponse)
async def industrial_heat_share(request: Request):
    """Build a shareable link encoding the current (edited) plant."""
    cookie_sid = request.cookies.get("sid")
    sid, session = sessions.get_or_create(cookie_sid, IndustrialHeat().build)
    form = await request.form()
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        session.plant = form_to_plant(session.plant, values)
    except ValueError as exc:
        return templates.TemplateResponse(request, "_share.jinja", {"error": str(exc)})
    url = f"{request.url_for('industrial_heat')}?p={share.encode(session.plant)}"
    response = templates.TemplateResponse(request, "_share.jinja", {"url": url})
    if sid != cookie_sid:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.post("/industrial_heat/solve")
async def industrial_heat_solve(request: Request) -> Response:
    """Record the edited plant and launch its solve in the background."""
    preset = IndustrialHeat()
    cookie_sid = request.cookies.get("sid")
    sid, session = sessions.get_or_create(cookie_sid, preset.build)
    form = await request.form()
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        session.plant = form_to_plant(session.plant, values)
    except ValueError as exc:
        session.report(ServerSentEvent(event="failed", raw_data=str(exc)))
    else:
        session.report(ServerSentEvent(event="start", raw_data=""))
        session.launch(session.plant, preset)
    response = Response(status_code=204)
    if sid != cookie_sid:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.get("/industrial_heat/events", response_class=EventSourceResponse)
async def industrial_heat_events(
    request: Request,
) -> AsyncIterator[ServerSentEvent]:
    """Stream the session's solve runs to the page as Server-Sent Events."""
    session = sessions.get(request.cookies.get("sid"))
    if session is None:
        yield ServerSentEvent(
            event="failed", raw_data="Session expired -- reload the page."
        )
        return
    async for event in session.events():
        yield event
