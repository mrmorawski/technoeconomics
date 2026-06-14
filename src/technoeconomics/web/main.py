from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")

app = FastAPI(
    redoc_url=None, docs_url="/api-docs", opeanapi_url="/api-docs/openapi.json"
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.jinja")


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request, "about.jinja")


@app.get("/docs", response_class=RedirectResponse)
async def docs(request: Request):
    return RedirectResponse(
        "https://mrmorawski.github.io/technoeconomics/getting-started/"
    )
