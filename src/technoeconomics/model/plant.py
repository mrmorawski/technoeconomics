"""Plant: the intermediate representation of a model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from technoeconomics.model.component import Component
from technoeconomics.model.structure import Bus

if TYPE_CHECKING:
    import pypsa


def _snake_case(name: str) -> str:
    """``"HeatPump"`` -> ``"heat_pump"`` -- fallback id base for a component type."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _assign_ids(components: list[Component]) -> None:
    """Fill in blank component ids in place, enumerating repeats within a type.

    Components carrying an explicit `id` keep it; blank ones get their type's
    `default_id` (or the snake-case class name), suffixed ``_2``, ``_3``, ... when
    the same base is used more than once. Suffixing skips any id already taken, so
    auto-generated ids never collide with explicit ones.
    """
    taken = {c.id for c in components if c.id}
    counts: dict[str, int] = {}
    for c in components:
        if c.id:
            continue
        base = c.default_id or _snake_case(type(c).__name__)
        counts[base] = counts.get(base, 0) + 1
        candidate = base if counts[base] == 1 else f"{base}_{counts[base]}"
        while candidate in taken:
            counts[base] += 1
            candidate = f"{base}_{counts[base]}"
        c.id = candidate
        taken.add(candidate)


def annual_snapshots(year: int = 2013, freq: str = "h") -> pd.DatetimeIndex:
    """Snapshots spanning one calendar year (hourly by default).

    Convenience for the common case; `Plant.snapshots` accepts any
    `pandas.DatetimeIndex`.
    """
    return pd.date_range(
        f"{year}-01-01", f"{year + 1}-01-01", freq=freq, inclusive="left"
    )


@dataclass
class Plant:
    """Editable description of a model -- the system of record.

    Attributes:
        name: Human-readable model name.
        snapshots: Optimisation horizon (use [`annual_snapshots`][] or any index).
        buses: Named nodes; several may share a carrier (e.g. multiple heat buses).
        components: Building blocks referencing `buses` directly. Components may omit
            `id`; blanks are filled from each type's `default_id` and enumerated
            (``heat_pump``, ``heat_pump_2``, ...) so every component ends up uniquely
            named.
    """

    name: str
    snapshots: pd.DatetimeIndex
    buses: list[Bus]
    components: list[Component]

    def __post_init__(self) -> None:
        """Resolve any blank component ids so every component is uniquely named."""
        _assign_ids(self.components)

    def build_network(self) -> pypsa.Network:
        """Compile this plant into a disposable PyPSA network ready to optimise.

        Registers a carrier for each bus (the energy carriers) and a distinct
        carrier per enabled component (named after its id), so per-component flows
        stay attributable. Then adds the buses and lets each enabled component
        expand itself.
        """
        import pypsa

        n = pypsa.Network()
        n.set_snapshots(self.snapshots)  # ty: ignore[invalid-argument-type]

        for carrier in {b.carrier for b in self.buses}:
            n.add("Carrier", carrier)
        for c in self.components:
            if c.enabled:
                n.add("Carrier", c.id)

        for b in self.buses:
            n.add("Bus", b.id, carrier=b.carrier)

        for c in self.components:
            if c.enabled:
                c.add_to_network(n)

        return n
