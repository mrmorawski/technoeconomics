"""FastAPI application: routes, a solve thread pool, and template wiring."""

from collections.abc import AsyncIterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from technoeconomics.backend.results import Number, Plot, numbers, plots
from technoeconomics.backend.template import IndustrialHeat
from technoeconomics.model.plant import Plant
from technoeconomics.web.forms import form_to_plant, plant_to_form

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Background solves: a small thread pool with each job's future kept by id for polling.
_pool = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, Future] = {}


def _solve(
    plant: Plant, number_reqs: list[Number], plot_reqs: list[Plot]
) -> dict:
    """Build, optimise, and read out a plant's results. Runs in a worker thread.

    Args:
        plant: The plant to solve.
        number_reqs: The headline numbers to compute.
        plot_reqs: The charts to compute.

    Returns:
        ``{"numbers": [...], "plots": [...]}`` -- ready for the page.

    Raises:
        RuntimeError: If the optimisation does not reach an optimal solution.
    """
    n = plant.build_network()
    status, condition = n.optimize(solver_name="highs")
    if status != "ok":
        raise RuntimeError(f"solve failed: status={status}, condition={condition}")
    n.sanitize()  # assign colours to any carriers that lack one
    return {"numbers": numbers(n, number_reqs), "plots": plots(n, plot_reqs)}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Shut the solve pool down cleanly when the app stops."""
    yield
    _pool.shutdown(cancel_futures=True)


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
    """Render the industrial-heat model page (schematic, generated form, solve)."""
    template = IndustrialHeat()
    return templates.TemplateResponse(
        request,
        "template.jinja",
        {
            "title": template.title,
            "description": template.description,
            "schematic": template.schematic_svg(),
            "components": plant_to_form(template.build()),
        },
    )


@app.post("/industrial_heat/solve", response_class=HTMLResponse)
async def solve_submit(request: Request):
    """Apply the form onto a fresh template plant, then queue a solve.

    The route's template (industrial heat) supplies the structure and the results to
    compute; the form supplies the edited parameters.
    """
    template = IndustrialHeat()
    form = await request.form()
    values = {k: v for k, v in form.items() if isinstance(v, str)}
    try:
        plant = form_to_plant(template.build(), values)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "_results.jinja", {"error": str(exc)}
        )
    job_id = uuid4().hex
    _jobs[job_id] = _pool.submit(
        _solve, plant, list(template.numbers), list(template.plots)
    )
    return templates.TemplateResponse(request, "_job.jinja", {"job_id": job_id})


@app.get("/solve/{job_id}", response_class=HTMLResponse)
async def solve_status(request: Request, job_id: str):
    """Report a solve job's state: keep polling, or swap in the result/error."""
    future = _jobs.get(job_id)
    if future is None:
        return templates.TemplateResponse(
            request, "_results.jinja", {"error": "Unknown or expired job."}
        )
    if not future.done():
        return templates.TemplateResponse(request, "_job.jinja", {"job_id": job_id})
    del _jobs[job_id]
    try:
        result = future.result()
    except Exception as exc:  # noqa: BLE001 -- surface any solve failure to the user
        return templates.TemplateResponse(
            request, "_results.jinja", {"error": str(exc)}
        )
    return templates.TemplateResponse(
        request,
        "_results.jinja",
        {"numbers": result["numbers"], "plots": result["plots"]},
    )
