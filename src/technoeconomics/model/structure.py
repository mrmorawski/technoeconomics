"""Structural primitives of a model: the balancing nodes components attach to."""

from __future__ import annotations

from dataclasses import dataclass

from technoeconomics.data.base import type_adapter


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
        """Reconstruct a bus from [`to_dict`][technoeconomics.model.structure.Bus.to_dict] output.

        Validated by the class's pydantic `TypeAdapter`, as it may come from an untrusted
        share link.

        Args:
            d: A dict with string ``id`` and ``carrier``.

        Returns:
            The reconstructed bus.

        Raises:
            ValueError: If `d` lacks a string ``id`` or ``carrier`` (pydantic's
                `ValidationError` is a `ValueError`).
        """
        if not isinstance(d, dict):
            raise ValueError("bus must be an object")
        return type_adapter(cls).validate_python(d)
