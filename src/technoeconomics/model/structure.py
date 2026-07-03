"""Structural primitives of a model: the balancing nodes components attach to."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bus:
    """A named balancing node, tagged with one energy carrier.

    Attributes:
        id: Unique bus name. Used as the PyPSA bus name when the plant is built.
        carrier: Energy carrier of the node (e.g. ``"electricity"``, ``"heat"``).
    """

    id: str
    carrier: str
