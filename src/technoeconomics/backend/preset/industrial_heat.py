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
    """Industrial process heat: grid power, a heat pump vs an electric boiler, a battery, heat demand."""

    name = "industrial_heat"
    title = "Industrial process heat"
    description = (
        "Grid electricity feeds a heat pump and an electric boiler, which compete to "
        "serve a varying heat demand, plus a battery. Edit the parameters and solve to "
        "see the optimal energy balances."
    )
    schematic = Path(__file__).parent / "schematics/industrial_heat.svg"
    plots: ClassVar[tuple[Plot, ...]] = (Plot.ENERGY_BALANCE,)
    numbers: ClassVar[tuple[Number, ...]] = (Number.PROJECT_COST,)

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
                    bus="electricity",
                    fixed=True,
                    plot_color=PlotColor.GREY,
                ),
                HeatPump(
                    id="heat_pump",
                    electricity_bus="electricity",
                    heat_bus="heat",
                    fixed=True,
                    plot_color=PlotColor.RED,
                ),
                ElectricBoiler(
                    id="electric_boiler",
                    electricity_bus="electricity",
                    heat_bus="heat",
                    plot_color=PlotColor.PURPLE,
                ),
                Battery(id="battery", bus="electricity", plot_color=PlotColor.GREEN),
                HeatDemand(
                    id="heat_demand",
                    bus="heat",
                    fixed=True,  # disabling the demand leaves a degenerate problem
                    load=Sinusoidal(mean=5, amplitude=4.0, period=24.0),
                    plot_color=PlotColor.ORANGE,
                ),
            ],
        )
