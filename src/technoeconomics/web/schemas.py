"""Response DTOs for the JSON API.

Plain dataclasses declared as the endpoints' return types so FastAPI emits a precise OpenAPI
schema -- the single source the frontend's TypeScript types are generated from
(``openapi-typescript``). Request bodies reuse [`Envelope`][technoeconomics.web.envelope.Envelope];
the form spec reuses the [`ComponentSpec`][technoeconomics.web.spec.ComponentSpec] dataclasses,
so those shapes are declared once and flow through to the client unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from technoeconomics.web.spec import ComponentSpec


@dataclass
class PresetSummary:
    """A preset in the picker list."""

    name: str
    title: str
    description: str


@dataclass
class PresetDetail:
    """A preset's presentation, default plant, and form spec (``GET /api/presets/{name}``)."""

    title: str
    description: str
    schematic_svg: str
    plant: dict[str, Any]
    form: list[ComponentSpec]


@dataclass
class RunResults:
    """A solved run's readout: curated headline numbers and chart configs (opaque to the API)."""

    numbers: list[Any]
    charts: list[Any]


@dataclass
class RunSnapshot:
    """A run's current state (``GET /api/runs/{id}``): status plus error or results when terminal."""

    status: str
    error: str | None = None
    results: RunResults | None = None


@dataclass
class RunAccepted:
    """The 202 body of a launched solve."""

    run_id: str


@dataclass
class ShareToken:
    """The body of ``POST /api/share``."""

    token: str


@dataclass
class FieldError:
    """One validation error, addressed to a spec path (or a component id)."""

    path: str
    message: str


@dataclass
class SolveErrors:
    """The 422 body of a rejected solve: the field-addressed validation errors."""

    errors: list[FieldError]
