"""Template presets: curated default plants plus their presentation.

Each template lives in its own module and subclasses
[`Template`][technoeconomics.backend.template.base.Template]. The registry below
discovers them so a route can look one up by name.
"""

from __future__ import annotations

from technoeconomics.backend.template.base import Template
from technoeconomics.backend.template.industrial_heat import IndustrialHeat

__all__ = ["IndustrialHeat", "Template", "get", "templates"]

_TEMPLATES: dict[str, type[Template]] = {
    IndustrialHeat.name: IndustrialHeat,
}


def templates() -> dict[str, type[Template]]:
    """All template presets, keyed by name."""
    return dict(_TEMPLATES)


def get(name: str) -> type[Template]:
    """Look a template preset up by name.

    Args:
        name: The template's [`name`][technoeconomics.backend.template.base.Template].

    Returns:
        The template class.

    Raises:
        KeyError: If no template has that name.
    """
    return _TEMPLATES[name]
