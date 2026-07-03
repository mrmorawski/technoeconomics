"""Plant: the intermediate representation of a model."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

import pandas as pd

from technoeconomics.data import resolve_datasets
from technoeconomics.model.component import AnyComponent, Component
from technoeconomics.model.structure import Bus
from technoeconomics.serialise import Snapshots, type_adapter

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


def _is_bus_ref(name: str) -> bool:
    """Bus-reference field naming convention: a field named ``bus`` or ending in ``_bus``."""
    return name == "bus" or name.endswith("_bus")


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
        components: Building blocks referencing `buses` by id. Components may omit
            `id`; blanks are filled from the snake-case class name and enumerated
            (``heat_pump``, ``heat_pump_2``, ...) so every component ends up uniquely
            named.
    """

    name: str
    snapshots: Snapshots
    buses: list[Bus]
    components: list[AnyComponent]

    def __post_init__(self) -> None:
        """Assign blank component ids and check referential integrity.

        Rejects duplicate bus ids, duplicate explicit component ids, and any bus
        reference (a component field named ``bus`` or ending in ``_bus``) that does not
        name a bus in `buses`. Runs on every construction, including the pydantic decode
        of an untrusted share link, so a malformed plant is refused at the boundary.

        Raises:
            ValueError: If bus ids collide, explicit component ids collide, or a component
                references a bus id absent from `buses`.
        """
        bus_ids = [b.id for b in self.buses]
        if len(bus_ids) != len(set(bus_ids)):
            raise ValueError("duplicate bus id")
        explicit = [c.id for c in self.components if c.id]
        if len(explicit) != len(set(explicit)):
            raise ValueError("duplicate component id")
        _assign_ids(self.components)
        known = set(bus_ids)
        for c in self.components:
            for f in fields(c):
                if _is_bus_ref(f.name):
                    ref = getattr(c, f.name)
                    if ref not in known:
                        raise ValueError(f"{c.id}.{f.name}: unknown bus {ref!r}")

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
        """Serialise to a JSON-able dict; round-trips through [`from_dict`][technoeconomics.model.plant.Plant.from_dict].

        The whole plant is one declared pydantic schema: buses become plain dicts, bus
        references stay bus ids, snapshots compress to ``{start, periods, freq}``, and each
        component/dataset is a class-name-tagged dict. The output is stamped with a schema
        version so old share links can be rejected rather than silently mis-decoded.
        """
        return {"v": 1, **type_adapter(Plant).dump_python(self, mode="json")}

    @classmethod
    def from_dict(cls, d: dict) -> Plant:
        """Reconstruct a plant from [`to_dict`][technoeconomics.model.plant.Plant.to_dict] output.

        The pydantic schema validates the structure and every field, and `__post_init__`
        checks referential integrity, so an invalid share link is rejected here rather than
        failing later at solve time.

        Args:
            d: A dict produced by [`to_dict`][technoeconomics.model.plant.Plant.to_dict].

        Returns:
            The reconstructed plant.

        Raises:
            ValueError: If `d` is not a dict, carries an unsupported schema version, or is
                not a valid plant (pydantic's `ValidationError` is itself a `ValueError`).
        """
        if not isinstance(d, dict):
            raise ValueError("plant must be an object")
        payload = dict(d)
        if payload.pop("v", None) != 1:
            raise ValueError("unsupported plant version")
        return type_adapter(cls).validate_python(payload)
