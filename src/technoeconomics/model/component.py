# TODO: add pytest-markdown-docs to test examples in docs
"""Component API and component directory for the model.

A model is composed of components connected through carriers.

```python
from technoeconomics.data import Constant, Sinusoidal

heat_pump = HeatPump(
    electricity_bus="electricity", heat_bus="heat", capex=Constant(900)
)
grid = GridElectricity(
    bus="electricity", price=Sinusoidal(mean=120, amplitude=40, period=24)
)
```
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, TYPE_CHECKING

from pydantic import ConfigDict

from technoeconomics.data import Scalar, ScalarDataset, SeriesDataset, Timeseries
from technoeconomics.model.params import (
    Advanced,
    Ge,
    Gt,
    Hidden,
    Label,
    Le,
    Lt,
    Param,
    Unit,
)
from technoeconomics.serialise import tagged_codec

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
class Component(ABC):
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

    Parameter fields are annotated with the vocabulary from
    [`technoeconomics.model.params`][] (unit, bounds, visibility), which the form-spec
    generator reads; a field that is not a numeric scalar or a dataset (e.g. a bus
    reference) must be marked ``Hidden``.

    Bus references are held as bus ids (strings) by name convention: a field named
    ``bus`` or ending in ``_bus`` is a reference to a bus in `Plant.buses`. The plant
    checks these on construction (every reference must name an existing bus).

    Attributes:
        id: Unique name within the plant; used as the PyPSA component name and as
            its own carrier, so results are attributable per component. Optional --
            if left blank, the plant assigns one from the snake-case class name,
            enumerating (e.g. ``heat_pump``, ``heat_pump_2``) when a type appears
            more than once.
        enabled: If False, the component is skipped when the network is built.
        fixed: If True, this component may not be disabled -- a property of its role
            in a preset, not of its class (set at preset assembly, e.g. a demand whose
            removal would leave a degenerate problem). A fixed component gets no enable
            toggle in the form, and a submission that tries to switch it off is rejected.
        plot_color: Colour for this component's flows in result plots. If None, PyPSA
            assigns one when the network is sanitised.
    """

    # Inherited by every component (authors never write it). ``arbitrary_types_allowed``
    # lets pydantic treat the ndarray/Series values a `Timeseries` field may hold as opaque;
    # ``extra="forbid"`` makes `Plant.from_dict` strict, so a stale or hand-written plant dict
    # fails loudly rather than silently dropping the keys it does not recognise.
    __pydantic_config__ = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    id: str = ""
    enabled: bool = True
    fixed: bool = False
    plot_color: PlotColor | None = None

    @abstractmethod
    def add_to_network(self, n: pypsa.Network) -> None:
        """Expand this component into one or more PyPSA elements on `n`.

        Called on a copy whose dataset fields have already been resolved, so
        ``self.<field>`` yields a concrete number or snapshot-aligned series.
        """


_component_validate, _component_dump = tagged_codec(Component)
type AnyComponent = Annotated[Component, _component_validate, _component_dump]
"""A component (de)serialised through the class-name-tagged subclass registry."""


@dataclass(kw_only=True)
class GridElectricity(Component):
    """Grid connection injecting electricity at a (possibly time-varying) price.

    Attributes:
        bus: Electricity bus to inject into.
        price: Marginal cost of electricity [EUR/MWh].
        max_capacity: Maximum injection power [MW].
        capex: Annuitised investment cost [EUR/MW].
    """

    bus: Param[str, Hidden]
    price: Param[Scalar | Timeseries | SeriesDataset, Unit("EUR/MWh")] = 120.0
    max_capacity: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("MW"), Advanced] = (
        1000.0
    )
    capex: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("EUR/MW"), Advanced] = 0.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Generator` injecting electricity at `price`."""
        n.add(
            "Generator",
            self.id,
            bus=self.bus,
            carrier=self.id,
            marginal_cost=self.price,
            capital_cost=self.capex,
            p_nom_max=self.max_capacity,
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

    electricity_bus: Param[str, Hidden]
    heat_bus: Param[str, Hidden]
    cop: Param[Param[Scalar, Gt(0)] | Timeseries | SeriesDataset, Label("COP")] = 3.0
    capex: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("EUR/MW"), Advanced] = (
        900000.0
    )

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Process` converting electricity (`rate0=-1`) to heat (`rate1=cop`)."""
        n.add(
            "Process",
            self.id,
            bus0=self.electricity_bus,
            bus1=self.heat_bus,
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

    electricity_bus: Param[str, Hidden]
    heat_bus: Param[str, Hidden]
    efficiency: Param[Scalar, Gt(0), Le(1)] | Timeseries | SeriesDataset = 0.99
    capex: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("EUR/MW"), Advanced] = 100.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Process` converting electricity to heat at `efficiency`."""
        n.add(
            "Process",
            self.id,
            bus0=self.electricity_bus,
            bus1=self.heat_bus,
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

    bus: Param[str, Hidden]
    max_hours: Param[Param[Scalar, Gt(0)] | ScalarDataset, Unit("h")] = 4.0
    capex: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("EUR/MW"), Advanced] = (
        12000.0
    )
    round_trip_efficiency: Param[
        Param[Scalar, Gt(0), Lt(1)] | ScalarDataset,
        Label("Round-trip efficiency"),
        Advanced,
    ] = 0.85

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `StorageUnit` on the electricity bus."""
        # add_to_network runs on a resolved copy, so the dataset field is a concrete float
        # here even though its declared type still admits a ScalarDataset.
        one_way = self.round_trip_efficiency**0.5  # ty: ignore[unsupported-operator]
        n.add(
            "StorageUnit",
            self.id,
            bus=self.bus,
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

    bus: Param[str, Hidden]
    load: Param[Param[Scalar, Ge(0)] | Timeseries | SeriesDataset, Unit("MW")] = 10.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Load` representing the heat demand."""
        n.add(
            "Load",
            self.id,
            bus=self.bus,
            carrier=self.id,
            p_set=self.load,
        )
