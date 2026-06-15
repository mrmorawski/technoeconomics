"""Templates: named presets that produce a default [`Plant`][technoeconomics.model.plant.Plant].

The template API mirrors the component API: a `Template` base class with subclasses
that define the preset in `build`. There is no registry object -- presets are
discovered via `Template.__subclasses__()` (see [`templates`][]). Templates are
defined in code, never parsed or stored. Turning a frontend form submission into a
`Plant` is a backend concern and lives there, not in the model.
"""

from typing import ClassVar

from technoeconomics.model.component import (
    Battery,
    GridElectricity,
    HeatDemand,
    HeatPump,
)
from technoeconomics.model.plant import Plant, annual_snapshots
from technoeconomics.model.structure import Bus


class Template:
    """Base for templates: subclass and implement `build`.

    Attributes:
        name: Stable identifier used to look the preset up (e.g. in a URL).
        title: Human-readable title.
    """

    name: ClassVar[str] = ""
    title: ClassVar[str] = ""

    def build(self) -> Plant:
        """Return a fresh default plant for this template."""
        raise NotImplementedError


class IndustrialHeat(Template):
    """Industrial process heat: grid electricity, a heat pump, a battery, heat demand."""

    name: ClassVar[str] = "industrial_heat"
    title: ClassVar[str] = "Industrial process heat"

    def build(self) -> Plant:
        """Build the default industrial-heat plant."""
        electricity = Bus(id="electricity", carrier="electricity")
        heat = Bus(id="heat", carrier="heat")
        return Plant(
            name=self.name,
            snapshots=annual_snapshots(2030),
            buses=[electricity, heat],
            components=[
                GridElectricity(id="grid", bus=electricity),
                HeatPump(id="heat_pump", electricity_bus=electricity, heat_bus=heat),
                Battery(id="battery", bus=electricity),
                HeatDemand(id="heat_demand", bus=heat),
            ],
        )


def templates() -> dict[str, type[Template]]:
    """All template presets, keyed by name (discovered from subclasses)."""
    return {t.name: t for t in Template.__subclasses__()}
