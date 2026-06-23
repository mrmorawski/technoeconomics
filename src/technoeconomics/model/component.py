# TODO: add pytest-markdown-docs to test examples in docs
"""Component API and component directory for the model.

A model is composed of components connected through carriers.

```python
from technoeconomics.data import Constant, Sinusoidal
from technoeconomics.model.structure import Bus

electricity = Bus(id="electricity", carrier="electricity")
heat = Bus(id="heat", carrier="heat")

heat_pump = HeatPump(electricity_bus=electricity, heat_bus=heat, capex=Constant(900))
grid = GridElectricity(bus=electricity, price=Sinusoidal(mean=120, amplitude=40, period=24))
```
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from technoeconomics.data import (
    Dataset,
    ScalarDataset,
    SeriesDataset,
    Timeseries,
    concrete_subclasses,
)
from technoeconomics.model.structure import Bus

if TYPE_CHECKING:
    import pypsa


class PlotColor(StrEnum):
    """A curated palette for component colours in result plots."""

    BLUE = "#1f77b4"
    ORANGE = "#ff7f0e"
    GREEN = "#2ca02c"
    RED = "#d62728"
    PURPLE = "#9467bd"
    BROWN = "#8c564b"
    PINK = "#e377c2"
    GREY = "#7f7f7f"
    OLIVE = "#bcbd22"
    CYAN = "#17becf"


@dataclass(kw_only=True)
class Component:
    """Base for all components: shared identity, serialisation, and the build contract.

    Currently components are a thin layer on top of [PyPSA Network Components](https://docs.pypsa.org/latest/user-guide/design/#network-components).

    Components can conceptually be divided into four main types:

    1. Input - inject energy into the system (e.g. grid electricity, gas connection, solar PV)
    2. Converter - turn one form of energy into another (e.g. heat pump, gas boiler)
    3. Storage - buffer energy in time (e.g. battery, thermal inertia of a house)
    4. Output - a demand or a loss, destroys energy (e.g. heat demand, heat loss in a house)

    The mapping to PyPSA is:

    | Component   | PyPSA component |
    |:-----------:|:---------------:|
    | `Input`     | `Generator`     |
    | `Converter` | `Process`       |
    | `Storage`   | `StorageUnit`   |
    | `Output`    | `Load`          |

    A component is a dataclass of technoeconomic parameters plus ``add_to_network()``
    -- a recipe for building a PyPSA component integrated into a model.

    Attributes:
        id: Unique name within the plant; used as the PyPSA component name and as
            its own carrier, so results are attributable per component. Optional --
            if left blank, the plant assigns one from the snake-case class name,
            enumerating (e.g. ``heat_pump``, ``heat_pump_2``) when a type appears
            more than once.
        enabled: If False, the component is skipped when the network is built.
        plot_color: Colour for this component's flows in result plots. If None, PyPSA
            assigns one when the network is sanitised.
    """

    id: str = ""
    enabled: bool = True
    plot_color: PlotColor | None = None

    def add_to_network(self, n: pypsa.Network) -> None:
        """Expand this component into one or more PyPSA elements on `n`.

        Called on a copy whose dataset fields have already been resolved, so
        ``self.<field>`` yields a concrete number or snapshot-aligned series.
        """
        raise NotImplementedError

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        out: dict = {"__type__": type(self).__name__}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Bus):
                out[f.name] = {"__bus__": v.id}
            elif isinstance(v, Dataset):
                out[f.name] = v.to_dict()
            elif isinstance(v, (pd.Series, np.ndarray)):
                out[f.name] = v.tolist()
            else:
                out[f.name] = v
        return out

    @classmethod
    def from_dict(cls, d: dict, buses: dict[str, Bus]) -> Component:
        """Reconstruct a component, relinking bus refs by id and rebuilding datasets.

        Args:
            d: A dict produced by [`to_dict`][technoeconomics.model.component.Component.to_dict].
            buses: The plant's buses keyed by id, used to relink bus references.

        Returns:
            The reconstructed component.
        """
        target = concrete_subclasses(Component)[d["__type__"]]
        kwargs: dict = {}
        for k, v in d.items():
            if k == "__type__":
                continue
            if isinstance(v, dict) and "__bus__" in v:
                kwargs[k] = buses[v["__bus__"]]
            elif isinstance(v, dict) and "__dataset__" in v:
                kwargs[k] = Dataset.from_dict(v)
            else:
                kwargs[k] = v
        return target(**kwargs)


@dataclass(kw_only=True)
class GridElectricity(Component):
    """Grid connection injecting electricity at a (possibly time-varying) price.

    Attributes:
        bus: Electricity bus to inject into.
        price: Marginal cost of electricity [EUR/MWh].
        max_capacity: Maximum injection power [MW].
        capex: Annuitised investment cost [EUR/MW].
    """

    bus: Bus
    price: float | Timeseries | SeriesDataset = 120.0
    max_capacity: float | ScalarDataset = field(default=1000, metadata={"advanced": True})
    capex: float | ScalarDataset = field(default=0, metadata={"advanced": True})

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Generator` injecting electricity at `price`."""
        n.add(
            "Generator",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            marginal_cost=self.price,
            capital_cost=self.capex,
            p_max=self.max_capacity,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class HeatPump(Component):
    """Electricity-to-heat conversion (a PyPSA `Process`) with a constant or varying COP.

    Attributes:
        electricity_bus: Bus the heat pump draws electricity from (input).
        heat_bus: Bus the heat pump delivers heat to (output).
        cop: Coefficient of performance.
        capex: Annuitised investment cost [EUR/MW of electricity input].
    """

    electricity_bus: Bus
    heat_bus: Bus
    cop: float | Timeseries | SeriesDataset = 3.0
    capex: float | ScalarDataset = field(default=900000.0, metadata={"advanced": True})

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Process` converting electricity (`rate0=-1`) to heat (`rate1=cop`)."""
        n.add(
            "Process",
            self.id,
            bus0=self.electricity_bus.id,
            bus1=self.heat_bus.id,
            carrier=self.id,
            rate1=self.cop,
            capital_cost=self.capex,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class ElectricBoiler(Component):
    """Electric resistance heating: cheap to install but ~unity efficiency.

    Attributes:
        electricity_bus: Bus the boiler draws electricity from (input).
        heat_bus: Bus the boiler delivers heat to (output).
        efficiency: Heat out per unit electricity in.
        capex: Annuitised investment cost [EUR/MW of electricity input].
    """

    electricity_bus: Bus
    heat_bus: Bus
    efficiency: float | Timeseries | SeriesDataset = 0.99
    capex: float | ScalarDataset = field(default=100.0, metadata={"advanced": True})

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Process` converting electricity to heat at `efficiency`."""
        n.add(
            "Process",
            self.id,
            bus0=self.electricity_bus.id,
            bus1=self.heat_bus.id,
            carrier=self.id,
            rate1=self.efficiency,
            capital_cost=self.capex,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class Battery(Component):
    """Electricity storage with a fixed energy-to-power ratio.

    Attributes:
        bus: Electricity bus the battery attaches to.
        max_hours: Storage duration at rated power [h].
        capex: Annuitised investment cost [EUR/MW].
        round_trip_efficiency: Fraction of stored energy returned over a full
            charge-discharge cycle. Split evenly across the two directions
            (``sqrt`` each way) when building the PyPSA `StorageUnit`. Must be
            < 1 -- a lossless battery makes simultaneous charge and discharge
            free, leaving the dispatch split degenerate (non-physical "wash").
    """

    bus: Bus
    max_hours: float | ScalarDataset = 4.0
    capex: float | ScalarDataset = field(default=12000.0, metadata={"advanced": True})
    round_trip_efficiency: float | ScalarDataset = field(default=0.85, metadata={"advanced": True})

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `StorageUnit` on the electricity bus."""
        # add_to_network runs on a resolved copy, so the dataset field is a concrete float
        # here even though its declared type still admits a ScalarDataset.
        one_way = self.round_trip_efficiency**0.5  # ty: ignore[unsupported-operator]
        n.add(
            "StorageUnit",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            max_hours=self.max_hours,
            capital_cost=self.capex,
            efficiency_store=one_way,
            efficiency_dispatch=one_way,
            cyclic_state_of_charge=True,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class HeatDemand(Component):
    """A heat demand (load) on a heat bus.

    Attributes:
        bus: Heat bus the demand is drawn from.
        load: Heat demand [MW].
    """

    bus: Bus
    load: float | Timeseries | SeriesDataset = 10.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Load` representing the heat demand."""
        n.add(
            "Load",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            p_set=self.load,
        )
