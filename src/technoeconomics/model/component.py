# TODO: add pytest-markdown-docs to test examples in docs
"""Component API and component directory for the model.

A model is composed of components connected through carriers.

Each technoeconomic parameter accepts either a literal value or a
[`Dataset`][technoeconomics.data.Dataset] -- a lazy, serialisable handle resolved
to a concrete value before the network is built -- so users need not source data
by hand. Each field spells out exactly what it accepts (mirroring the
``float | pd.Series`` values PyPSA itself takes), so the choice is explicit and the
type checker enforces it:

- a scalar parameter: ``float | ScalarDataset``
- a time-varying parameter: ``float | Timeseries | SeriesDataset`` (a constant
  ``float`` broadcasts; [`Timeseries`][technoeconomics.data.Timeseries] is
  ``np.ndarray | pd.Series | Sequence[float]``)

A field may of course be narrower (e.g. just ``float``). Passing a ``SeriesDataset``
where a ``ScalarDataset`` is expected is a type error.

Authoring a component is just writing a dataclass of parameters plus
``add_to_network``. By the time it runs, every field already holds a concrete value
(resolution happens once in the model -- see
[`resolve_datasets`][technoeconomics.data.resolve_datasets]), so the method simply
reads ``self.<field>``; it never touches the data layer. Serialisation is inherited.

```python
from technoeconomics.data import Constant, Sinusoidal
from technoeconomics.model.structure import Bus

electricity = Bus(id="electricity", carrier="electricity")
heat = Bus(id="heat", carrier="heat")

heat_pump = HeatPump(electricity_bus=electricity, heat_bus=heat, capex=Constant(900))
grid = GridElectricity(
    bus=electricity, price=Sinusoidal(mean=120, amplitude=40, period=24)
)
```
"""

from __future__ import annotations

from dataclasses import dataclass, fields
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
    """

    id: str = ""
    enabled: bool = True

    def add_to_network(self, n: pypsa.Network) -> None:
        """Expand this component into one or more PyPSA elements on `n`.

        Called on a copy whose dataset fields have already been resolved, so
        ``self.<field>`` yields a concrete number or snapshot-aligned series.
        """
        raise NotImplementedError

    def to_dict(self) -> dict:
        """Serialise to a plain dict.

        Bus refs become ids, unresolved datasets become tagged dicts, and resolved
        arrays (from a resolved plant) become plain lists; floats pass through. The
        same method therefore serialises both a recipe plant (dataset specs) and a
        resolved plant (values baked in).
        """
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
    """

    bus: Bus
    price: float | Timeseries | SeriesDataset = 120.0

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
    capex: float | ScalarDataset = 900.0

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
        bus: Electricity bus the battery attaches to.
        max_hours: Storage duration at rated power [h].
        capex: Annuitised investment cost [EUR/MW].
    """

    bus: Bus
    max_hours: float | ScalarDataset = 4.0
    capex: float | ScalarDataset = 12000.0

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
