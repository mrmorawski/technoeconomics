"""Preset base: a curated preset pairing a default plant with how to present it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from technoeconomics.backend.results import Number, Plot
from technoeconomics.model.plant import Plant


class Preset(ABC):
    """A named preset: a default plant plus its presentation.

    The preset *completes* a model: alongside the default plant and its copy it
    declares which results to present -- the `plots` and `numbers` the frontend should
    show once the plant is solved.

    A preset is a class, not a dataclass, so these are ordinary class attributes: a subclass
    overrides them with a bare assignment and inherits the declared type from here. The
    ``ClassVar`` on the two sequences is what marks them as shared class state rather than
    per-instance defaults; the scalars need no restating.

    Attributes:
        name: Stable identifier used to look the preset up (e.g. in a URL).
        title: Human-readable title.
        description: Short blurb shown above the model.
        schematic: Path to an SVG drawing of the plant, or None for no drawing.
        plots: The charts to render from a solve, in display order. A tuple: it is shared by
            every instance of the preset, so it must not be mutable.
        numbers: The headline numbers to render from a solve, in display order. A tuple, for
            the same reason as `plots`.
    """

    name: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    schematic: ClassVar[Path | None] = None
    plots: ClassVar[tuple[Plot, ...]] = ()
    numbers: ClassVar[tuple[Number, ...]] = ()

    @abstractmethod
    def build(self) -> Plant:
        """Return a fresh default plant for this preset."""

    def schematic_svg(self) -> str:
        """Read the schematic SVG so it can be inlined into the page.

        Returns:
            The SVG markup, or an empty string when the preset declares no schematic (the
            client renders the drawing only when there is one).
        """
        return self.schematic.read_text(encoding="utf-8") if self.schematic else ""
