# TODO: add pytest-markdown-docs to test examples in docs
"""Component API and component directory for the model.

A model is composed of components connected through carriers.

``Component``, combined with ``Dataset``, enables for easy construction of
reusable and composable blocks, and for quickly building models. Users don't need to worry about
specifics of modelling a given technology, and don't need to source data for it.

For example, grid electricity for an industrial consumer in Spain can be modelled as:

```python
from technoeconomics.data import GridElectricityDataset

grid_electricity = GridElectricity(
    price=GridElectricityDataset(loc=(40, -4), consumer_type="industrial")
)
```

A residential air source heat pump located in Germany:

```python
from technoeconomics.data import WeatherDataset, CostDataset

heat_pump = HeatPump(
    price=CostDataset(
        item="heat_pump.residential",
        T_supply=20,
        T_demand=WeatherDataset("temp_surface", loc=(52, 13)),
    )
)
```

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from technoeconomics.model.structure import Bus

if TYPE_CHECKING:
    import pypsa


@dataclass(kw_only=True)
class Component:
    """Base for all components: shared identity plus the build contract.

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

    A component is dataclass containing relevant technoeconomic parameters, and
    ``add_to_network()`` - a recipe for building a PyPSA component integrated into a model.

    Attributes:
        default_id: Base name used to auto-generate `id`. Defaults to the snake-case
            class name when left blank (see [`Plant`][technoeconomics.model.plant.Plant]).
        id: Unique name within the plant; used as the PyPSA component name and as
            its own carrier, so results are attributable per component. Optional --
            if left blank, the plant assigns one from `default_id`, enumerating
            (e.g. ``heat_pump``, ``heat_pump_2``) when a type appears more than once.
        enabled: If False, the component is skipped when the network is built.
    """

    default_id: ClassVar[str] = ""

    id: str = ""
    enabled: bool = True

    def add_to_network(self, n: pypsa.Network) -> None:
        """Expand this component into one or more PyPSA elements on `n`."""
        raise NotImplementedError


@dataclass(kw_only=True)
class GridElectricity(Component):
    """Grid connection injecting electricity at a constant price.

    Attributes:
        default_id: Base name used to auto-generate `id`.
        bus: Electricity bus to inject into.
        price: Marginal cost of electricity [EUR/MWh].
    """

    default_id: ClassVar[str] = "grid"

    bus: Bus
    price: float = 120.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Generator` injecting electricity at `price`."""
        n.add(
            "Generator",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            marginal_cost=self.price,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class HeatPump(Component):
    """Electricity-to-heat conversion (a PyPSA `Process`) with a constant COP.

    Attributes:
        default_id: Base name used to auto-generate `id`.
        electricity_bus: Bus the heat pump draws electricity from (input).
        heat_bus: Bus the heat pump delivers heat to (output).
        cop: Coefficient of performance.
        capex: Annuitised investment cost [EUR/MW of electricity input].
    """

    default_id: ClassVar[str] = "heat_pump"

    electricity_bus: Bus
    heat_bus: Bus
    cop: float = 3.0
    capex: float = 900.0

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
class Battery(Component):
    """Electricity storage with a fixed energy-to-power ratio.

    Attributes:
        default_id: Base name used to auto-generate `id`.
        bus: Electricity bus the battery attaches to.
        max_hours: Storage duration at rated power [h].
        capex: Annuitised investment cost [EUR/MW].
    """

    default_id: ClassVar[str] = "battery"

    bus: Bus
    max_hours: float = 4.0
    capex: float = 12000.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `StorageUnit` on the electricity bus."""
        n.add(
            "StorageUnit",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            max_hours=self.max_hours,
            capital_cost=self.capex,
            cyclic_state_of_charge=True,
            p_nom_extendable=True,
        )


@dataclass(kw_only=True)
class HeatDemand(Component):
    """A heat demand (load) on a heat bus.

    Attributes:
        default_id: Base name used to auto-generate `id`.
        bus: Heat bus the demand is drawn from.
        load: Heat demand [MW].
    """

    default_id: ClassVar[str] = "heat_demand"

    bus: Bus
    load: float = 10.0

    def add_to_network(self, n: pypsa.Network) -> None:
        """Add a `Load` representing the heat demand."""
        n.add(
            "Load",
            self.id,
            bus=self.bus.id,
            carrier=self.id,
            p_set=self.load,
        )
