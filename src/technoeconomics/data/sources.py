"""Concrete datasets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from technoeconomics.data.base import Dataset


@dataclass(frozen=True)
class Constant(Dataset[float]):
    """A single fixed value.

    Attributes:
        value: The constant to return.
    """

    value: float

    def compute(self, _snapshots: pd.DatetimeIndex) -> float:
        """Return ``value``."""
        return float(self.value)


@dataclass(frozen=True)
class Sinusoidal(Dataset[pd.Series]):
    """A sine wave over the snapshots -- a stand-in for daily/seasonal shapes.

    The value at time ``t`` is ``mean + amplitude * sin(2*pi * (h - phase) /
    period)``, where ``h`` is the number of hours since the first snapshot.

    Attributes:
        mean: Baseline the wave oscillates around.
        amplitude: Peak deviation from ``mean``.
        period: Oscillation period in hours (e.g. ``24`` daily, ``8760`` yearly).
        phase: Horizontal shift in hours.
    """

    mean: float
    amplitude: float
    period: float = 24.0
    phase: float = 0.0

    def compute(self, snapshots: pd.DatetimeIndex) -> pd.Series:
        """Return the sine wave sampled at ``snapshots``."""
        hours = np.asarray((snapshots - snapshots[0]) / pd.Timedelta(hours=1), dtype=float)
        values = self.mean + self.amplitude * np.sin(2 * np.pi * (hours - self.phase) / self.period)
        return pd.Series(values, index=snapshots)
