"""The uniform client envelope: a preset plus the user's overlay edits and enable toggles.

One type for the whole client contract -- the solve and share request bodies and the share-link
codec all carry the same ``{preset, overlay, enabled}``. A plain frozen dataclass validated at
the boundary by pydantic (FastAPI for request bodies, `TypeAdapter` for the share codec),
consistent with the model layer's plain-dataclass style.

Only the envelope's *shape* is checked here (preset is a string, overlay values are numbers,
enable toggles are booleans, no unknown keys). Its *meaning* -- that overlay paths are real spec
paths and values are in bounds -- is enforced at solve against the preset spec by
[`validate_edits`][technoeconomics.web.spec.validate_edits], not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ConfigDict


@dataclass(frozen=True)
class Envelope:
    """A preset plus the user's overlay edits and enable toggles.

    Attributes:
        preset: The preset name the overlay applies over.
        overlay: ``{spec_path: value}`` scalar edits.
        enabled: ``{component_id: bool}`` enable toggles.
    """

    # extra="forbid" rejects unknown keys when validating an untrusted body or share link.
    __pydantic_config__ = ConfigDict(extra="forbid")

    preset: str
    overlay: dict[str, float] = field(default_factory=dict)
    enabled: dict[str, bool] = field(default_factory=dict)
