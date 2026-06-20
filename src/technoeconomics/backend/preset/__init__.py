"""Presets: curated default plants plus their presentation.

Each preset lives in its own module and subclasses
[`Preset`][technoeconomics.backend.preset.base.Preset]. The registry below
discovers them so a route can look one up by name.
"""

from __future__ import annotations

from technoeconomics.backend.preset.base import Preset
from technoeconomics.backend.preset.industrial_heat import IndustrialHeat

__all__ = ["IndustrialHeat", "Preset", "get", "presets"]

_PRESETS: dict[str, type[Preset]] = {
    IndustrialHeat.name: IndustrialHeat,
}


def presets() -> dict[str, type[Preset]]:
    """All presets, keyed by name."""
    return dict(_PRESETS)


def get(name: str) -> type[Preset]:
    """Look a preset up by name.

    Args:
        name: The preset's [`name`][technoeconomics.backend.preset.base.Preset].

    Returns:
        The preset class.

    Raises:
        KeyError: If no preset has that name.
    """
    try:
        return _PRESETS[name]
    except KeyError:
        raise KeyError(
            f"unknown preset {name!r}; available: {sorted(_PRESETS)}"
        ) from None
