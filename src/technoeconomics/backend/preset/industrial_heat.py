"""The industrial process heat preset."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from technoeconomics.backend.preset.base import Preset
from technoeconomics.backend.results import Number, Plot
from technoeconomics.data import Sinusoidal
from technoeconomics.model.component import (
    Battery,
    ElectricBoiler,
    GridElectricity,
    HeatDemand,
    HeatPump,
    PlotColor,
)
from technoeconomics.model.plant import Plant, annual_snapshots
from technoeconomics.model.structure import Bus


class IndustrialHeat(Preset):
    """Industrial process heat with grid power, heat conversion, battery, and heat demand."""

    name: ClassVar[str] = "industrial_heat"
    title: ClassVar[str] = "Industrial process heat"
    description: ClassVar[str] = (
        "Grid electricity feeds a heat pump and an electric boiler, which compete to "
        "serve a varying heat demand, plus a battery. Edit the parameters and solve to "
        "see the optimal energy balances."
    )
    schematic: ClassVar[Path] = Path(__file__).parent / "schematics/industrial_heat.svg"
    plots: ClassVar[list[Plot]] = [Plot.ENERGY_BALANCE]
    numbers: ClassVar[list[Number]] = [Number.PROJECT_COST]

    def build(self) -> Plant:
        """Build the default industrial-heat plant."""
        electricity = Bus(id="electricity", carrier="electricity")
        heat = Bus(id="heat", carrier="heat")
        return Plant(
            name=self.name,
            snapshots=annual_snapshots(2030),
            buses=[electricity, heat],
            components=[
                GridElectricity(
                    id="grid",
                    price=Sinusoidal(mean=100, amplitude=50, period=24),
                    max_capacity=100,
                    capex=1000000,
                    bus=electricity,
                    plot_color=PlotColor.GREY,
                ),
                HeatPump(
                    id="heat_pump",
                    electricity_bus=electricity,
                    heat_bus=heat,
                    plot_color=PlotColor.RED,
                ),
                ElectricBoiler(
                    id="electric_boiler",
                    electricity_bus=electricity,
                    heat_bus=heat,
                    plot_color=PlotColor.PURPLE,
                ),
                Battery(id="battery", bus=electricity, plot_color=PlotColor.GREEN),
                HeatDemand(
                    id="heat_demand",
                    bus=heat,
                    load=Sinusoidal(mean=5, amplitude=4.0, period=24.0),
                    plot_color=PlotColor.ORANGE,
                ),
            ],
        )
