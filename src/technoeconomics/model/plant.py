"""Plant: the intermediate representation of a model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from technoeconomics.data import resolve_datasets
from technoeconomics.model.component import Component
from technoeconomics.model.structure import Bus

if TYPE_CHECKING:
    import pypsa


def _snake_case(name: str) -> str:
    """``"HeatPump"`` -> ``"heat_pump"`` -- fallback id base for a component type."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _assign_ids(components: list[Component]) -> None:
    """Fill in blank component ids in place, enumerating repeats within a type.

    Components carrying an explicit `id` keep it; blank ones get the snake-case
    class name, suffixed ``_2``, ``_3``, ... when the same base is used more than
    once. Suffixing skips any id already taken, so auto-generated ids never collide
    with explicit ones.
    """
    taken = {c.id for c in components if c.id}
    counts: dict[str, int] = {}
    for c in components:
        if c.id:
            continue
        base = _snake_case(type(c).__name__)
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
    return pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq=freq, inclusive="left")


@dataclass
class Plant:
    """Editable description of a model -- the system of record.

    Attributes:
        name: Human-readable model name.
        snapshots: Optimisation horizon (use [`annual_snapshots`][] or any index).
        buses: Named nodes; several may share a carrier (e.g. multiple heat buses).
        components: Building blocks referencing `buses` directly. Components may omit
            `id`; blanks are filled from the snake-case class name and enumerated
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
        stay attributable. Adds the buses, then resolves the enabled components'
        dataset fields to concrete values (caching so each distinct input is
        computed once) and lets each expand itself.
        """
        import pypsa

        n = pypsa.Network()
        n.set_snapshots(self.snapshots)  # ty: ignore[invalid-argument-type]

        enabled = [c for c in self.components if c.enabled]

        for carrier in {b.carrier for b in self.buses}:
            n.add("Carrier", carrier)
        for c in enabled:
            n.add("Carrier", c.id, **({"color": c.plot_color} if c.plot_color else {}))

        for b in self.buses:
            n.add("Bus", b.id, carrier=b.carrier)

        for c in resolve_datasets(enabled, self.snapshots):
            c.add_to_network(n)

        return n

    def to_dict(self) -> dict:
        """Serialise to a JSON-able dict.

        Delegates to each bus's and component's own ``to_dict``; bus references on
        components are encoded as bus ids and data-source fields as tagged dicts.
        """
        return {
            "name": self.name,
            "snapshots": _snapshots_to_dict(self.snapshots),
            "buses": [b.to_dict() for b in self.buses],
            "components": [c.to_dict() for c in self.components],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Plant:
        """Reconstruct a plant from [`to_dict`][technoeconomics.model.plant.Plant.to_dict] output.

        Buses are rebuilt first and indexed by id, so component bus references can
        be relinked to the same `Bus` objects the plant holds. A component
        referencing a bus id absent from `d["buses"]` raises `KeyError`, flagging
        the dangling reference.
        """
        buses = [Bus.from_dict(b) for b in d["buses"]]
        by_id = {b.id: b for b in buses}
        return cls(
            name=d["name"],
            snapshots=_snapshots_from_dict(d["snapshots"]),
            buses=buses,
            components=[Component.from_dict(c, by_id) for c in d["components"]],
        )


def _snapshots_to_dict(index: pd.DatetimeIndex) -> dict:
    """Encode a snapshot index compactly (by freq when regular, else explicit values)."""
    if index.freq is not None:
        return {
            "start": index[0].isoformat(),
            "periods": len(index),
            "freq": index.freqstr,
        }
    return {"values": [t.isoformat() for t in index]}


def _snapshots_from_dict(d: dict) -> pd.DatetimeIndex:
    """Rebuild a snapshot index from `_snapshots_to_dict` output."""
    if "values" in d:
        return pd.DatetimeIndex(d["values"])
    return pd.date_range(start=d["start"], periods=d["periods"], freq=d["freq"])
