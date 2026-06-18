"""Preset base: a curated preset pairing a default plant with how to present it."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from technoeconomics.backend.results import Number, Plot
from technoeconomics.model.plant import Plant


class Preset:
    """A named preset: a default plant plus its presentation.

    The preset *completes* a model: alongside the default plant and its copy it
    declares which results to present -- the `plots` and `numbers` the frontend should
    show once the plant is solved.

    Attributes:
        name: Stable identifier used to look the preset up (e.g. in a URL).
        title: Human-readable title.
        description: Short blurb shown above the model.
        schematic: Path to an SVG drawing of the plant.
        plots: The charts to render from a solve, in display order.
        numbers: The headline numbers to render from a solve, in display order.
    """

    name: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    schematic: ClassVar[Path]
    plots: ClassVar[list[Plot]] = []
    numbers: ClassVar[list[Number]] = []

    def build(self) -> Plant:
        """Return a fresh default plant for this preset."""
        raise NotImplementedError

    def schematic_svg(self) -> str:
        """Read the schematic SVG so it can be inlined into the page."""
        return self.schematic.read_text(encoding="utf-8")
