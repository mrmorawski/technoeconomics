"""The JSON API: registry-driven endpoints wiring the spec generator to the run store.

Overlay-solve throughout: the client posts ``{preset, overlay, enabled}``; the server rebuilds
from the *trusted* preset default, validates and applies the whitelisted edits, and launches a
run. Results are a GET-able resource on the run; progress streams over SSE (progress-only, one
terminal poke, then the server closes the stream). No preset is hardcoded -- everything is keyed
off the preset registry, so a new preset is picked up with no changes here.

Throttling is day-one API shape:

- **Single-flight** on a client-generated UUID (``X-Client-Id``): a client with a run already in
  flight gets 409 -- a common path (two tabs share one UUID), handled politely, not a hardening
  measure.
- **Caps** spoofing can't bypass: a per-IP concurrency cap (``N > 1``, tolerating campus NAT) and
  a global live-run cap, both 429 + ``Retry-After``.

In-flight bookkeeping is pruned lazily against the run store on each solve, so it needs no
completion callback and cannot leak entries.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from technoeconomics.backend import preset as registry
from technoeconomics.web import share as share_codec
from technoeconomics.web.envelope import Envelope
from technoeconomics.web.runs import RunManager
from technoeconomics.web.schemas import (
    PresetDetail,
    PresetSummary,
    RunAccepted,
    RunResults,
    RunSnapshot,
    ShareToken,
    SolveErrors,
)
from technoeconomics.web.spec import apply_edits, plant_to_spec, validate_edits

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from technoeconomics.backend.preset import Preset
    from technoeconomics.web.runs import Run

log = logging.getLogger(__name__)

# Live-run caps. Single-flight bounds a well-behaved client to one run; these bound abuse and
# load: a whole NAT'd department shares one egress IP, so the per-IP cap is > 1.
_GLOBAL_LIVE_CAP = 16
_PER_IP_LIVE_CAP = 3
_RETRY_AFTER = "10"


def _telemetry(run: Run) -> None:
    """Log a run's outcome at completion -- the seam a solve-telemetry store slots into later."""
    log.info(
        "run=%s preset=%s outcome=%s duration=%.2fs",
        run.id,
        run.preset_name,
        run.status,
        time.monotonic() - run.started,
    )


manager = RunManager(on_complete=_telemetry)
router = APIRouter(prefix="/api")


@dataclass
class _InFlight:
    """Bookkeeping for one accepted-but-unfinished run, for single-flight and the caps."""

    client_id: str
    ip: str


_inflight: dict[str, _InFlight] = {}


def _prune() -> None:
    """Drop bookkeeping for runs that are no longer live (self-cleaning, no callback needed)."""
    for run_id in list(_inflight):
        run = manager.get(run_id)
        if run is None or run.status != "running":
            del _inflight[run_id]


def _admit(client_id: str, ip: str) -> None:
    """Raise 409/429 if a new run is not allowed for this client/IP; return otherwise."""
    _prune()
    if client_id and any(f.client_id == client_id for f in _inflight.values()):
        raise HTTPException(409, "a solve is already running in another tab")
    if len(_inflight) >= _GLOBAL_LIVE_CAP:
        raise HTTPException(
            429,
            "the server is busy; try again shortly",
            headers={"Retry-After": _RETRY_AFTER},
        )
    if ip and sum(1 for f in _inflight.values() if f.ip == ip) >= _PER_IP_LIVE_CAP:
        raise HTTPException(
            429,
            "too many concurrent solves from your network",
            headers={"Retry-After": _RETRY_AFTER},
        )


def _preset(name: str, *, code: int = 404) -> Preset:
    """Instantiate the named preset, or raise an HTTP error with `code`."""
    try:
        return registry.get(name)()
    except KeyError as e:
        raise HTTPException(code, f"unknown preset {name!r}") from e


@router.get("/presets")
def list_presets() -> list[PresetSummary]:
    """List every preset for the picker."""
    return [
        PresetSummary(name=p.name, title=p.title, description=p.description)
        for p in registry.presets().values()
    ]


@router.get("/presets/{name}")
def get_preset(name: str) -> PresetDetail:
    """A preset's presentation, default plant, and form spec for the client to render."""
    preset = _preset(name)
    plant = preset.build()
    return PresetDetail(
        title=preset.title,
        description=preset.description,
        schematic_svg=preset.schematic_svg(),
        plant=plant.to_dict(),
        form=plant_to_spec(plant),
    )


@router.post(
    "/solve",
    status_code=202,
    response_model=RunAccepted,
    responses={422: {"model": SolveErrors}},
)
async def solve(
    req: Envelope,
    request: Request,
    x_client_id: Annotated[str | None, Header()] = None,
) -> RunAccepted | JSONResponse:
    """Validate and apply an overlay onto the preset default, then launch a run.

    Returns 202 ``{run_id}`` on success; 422 ``{errors}`` for an invalid overlay path or an
    out-of-bounds value; 409 if this client already has a run in flight; 429 if a cap is hit.
    """
    preset = _preset(req.preset, code=422)
    base = preset.build()
    spec = plant_to_spec(base)
    errors = validate_edits(spec, req.overlay, req.enabled)
    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})
    client_id = x_client_id or ""
    ip = request.client.host if request.client else ""
    _admit(client_id, ip)
    plant = apply_edits(base, req.overlay, req.enabled)
    run = manager.launch(plant, preset)
    _inflight[run.id] = _InFlight(client_id=client_id, ip=ip)
    return RunAccepted(run_id=run.id)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> RunSnapshot:
    """A run's status and, once done, its results (``{numbers, charts}``)."""
    run = manager.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown or expired run")
    snap = run.snapshot()
    results = snap.get("results")
    return RunSnapshot(
        status=snap["status"],
        error=snap.get("error"),
        results=RunResults(numbers=results["numbers"], charts=results["charts"])
        if results
        else None,
    )


@router.get(
    "/runs/{run_id}/events",
    response_class=EventSourceResponse,
    response_model=None,
)
async def run_events(run_id: str, request: Request) -> AsyncIterator[ServerSentEvent]:
    """Stream a run's progress as SSE, resuming from ``Last-Event-ID`` on reconnect.

    Progress-only: the stream carries progress lines and one terminal ``done``/``failed`` poke,
    then ends (the client GETs the result). An unknown/expired run yields one ``failed`` event
    rather than a 404, so the browser's `EventSource` does not reconnect into a loop.
    """
    run = manager.get(run_id)
    if run is None:
        yield ServerSentEvent(event="failed", raw_data="run not found or expired")
        return
    header = request.headers.get("Last-Event-ID")
    last_id = int(header) if header is not None and header.isdigit() else None
    async for event in run.events(last_id):
        yield event


@router.post("/share")
def create_share(req: Envelope) -> ShareToken:
    """Encode a ``{preset, overlay, enabled}`` envelope to a share token."""
    _preset(req.preset, code=422)  # only a known preset can be shared
    return ShareToken(token=share_codec.encode(req))


@router.get("/share/{token}")
def read_share(token: str) -> Envelope:
    """Decode a share token back to its ``{preset, overlay, enabled}`` envelope."""
    try:
        return share_codec.decode(token)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
