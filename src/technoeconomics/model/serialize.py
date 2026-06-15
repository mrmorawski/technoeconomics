"""Serialise a [`Plant`][technoeconomics.model.plant.Plant] to a plain dict and back."""

from dataclasses import fields
from typing import Any, get_type_hints

import pandas as pd

from technoeconomics.model.component import Component
from technoeconomics.model.plant import Plant
from technoeconomics.model.structure import Bus


def _component_classes() -> dict[str, type[Component]]:
    """All Component subclasses (recursively), keyed by class name."""

    def walk(base: type[Component]) -> list[type[Component]]:
        out: list[type[Component]] = []
        for cls in base.__subclasses__():
            out.append(cls)
            out.extend(walk(cls))
        return out

    return {cls.__name__: cls for cls in walk(Component)}


def plant_to_dict(plant: Plant) -> dict:
    """Serialise a plant to a JSON-able dict.

    Args:
        plant: The plant to serialise.

    Returns:
        A plain dict (JSON-able) carrying the plant's name, snapshots, buses, and
        components; round-trips through [`plant_from_dict`][]. Bus references on
        components are encoded as bus ids.
    """
    return {
        "name": plant.name,
        "snapshots": _snapshots_to_dict(plant.snapshots),
        "buses": [{"id": b.id, "carrier": b.carrier} for b in plant.buses],
        "components": [_component_to_dict(c) for c in plant.components],
    }


def plant_from_dict(d: dict) -> Plant:
    """Reconstruct a plant from `plant_to_dict` output.

    Buses are rebuilt first and indexed by id, so component bus references can be
    relinked to the same `Bus` objects the plant holds. A component referencing a
    bus id absent from `d["buses"]` surfaces a `KeyError` at load time, flagging
    the dangling reference.

    Args:
        d: A dict produced by [`plant_to_dict`][] (or matching its shape).

    Returns:
        The reconstructed plant.
    """
    buses = [Bus(id=b["id"], carrier=b["carrier"]) for b in d["buses"]]
    by_id = {b.id: b for b in buses}
    return Plant(
        name=d["name"],
        snapshots=_snapshots_from_dict(d["snapshots"]),
        buses=buses,
        components=[_component_from_dict(c, by_id) for c in d["components"]],
    )


def _component_to_dict(c: Component) -> dict[str, Any]:
    """Serialise a component, encoding any `Bus`-valued field as its id."""
    out: dict[str, Any] = {"type": type(c).__name__}
    for f in fields(c):
        v = getattr(c, f.name)
        out[f.name] = v.id if isinstance(v, Bus) else v
    return out


def _component_from_dict(d: dict, buses: dict[str, Bus]) -> Component:
    """Rebuild a component, resolving `Bus`-typed fields from `buses` by id."""
    cls = _component_classes()[d["type"]]
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {
        k: (buses[v] if hints.get(k) is Bus else v) for k, v in d.items() if k != "type"
    }
    return cls(**kwargs)


def _snapshots_to_dict(index: pd.DatetimeIndex) -> dict:
    if index.freq is not None:
        return {
            "start": index[0].isoformat(),
            "periods": len(index),
            "freq": index.freqstr,
        }
    return {"values": [t.isoformat() for t in index]}


def _snapshots_from_dict(d: dict) -> pd.DatetimeIndex:
    if "values" in d:
        return pd.DatetimeIndex(d["values"])
    return pd.date_range(start=d["start"], periods=d["periods"], freq=d["freq"])
