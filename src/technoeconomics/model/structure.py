"""Structural primitives of a model: the balancing nodes components attach to."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class Bus:
    """A named balancing node, tagged with one energy carrier.

    Attributes:
        id: Unique bus name. Used as the PyPSA bus name when the plant is built.
        carrier: Energy carrier of the node (e.g. ``"electricity"``, ``"heat"``).
    """

    id: str
    carrier: str

    def to_dict(self) -> dict:
        """Serialise to a plain dict; round-trips through [`from_dict`][technoeconomics.model.structure.Bus.from_dict]."""
        return {"id": self.id, "carrier": self.carrier}

    @classmethod
    def from_dict(cls, d: dict) -> Bus:
        """Reconstruct a bus from [`to_dict`][technoeconomics.model.structure.Bus.to_dict] output."""
        return cls(id=d["id"], carrier=d["carrier"])
