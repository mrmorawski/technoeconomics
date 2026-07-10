"""Uses [atlite](https://atlite.readthedocs.io) to download weather data for a location.

A subset of datasets it cached on disk for faster access, the rest is downloaded as needed.
"""

from dataclasses import dataclass

import atlite
import pandas as pd

from technoeconomics.data.base import Dataset
from technoeconomics.serialise import _snapshots_to_dict


@dataclass(frozen=True)
class Temperature(Dataset[pd.Series]):
    """Return temperature data via atlite.

    Attributes:
        lat: latitude of the location
        lon: longitude of the location
    """

    lat: float
    lon: float

    def compute(self, snapshots: pd.DatetimeIndex) -> pd.Series:
        """Get temperature data via atlite."""
        snapshot_dict = _snapshots_to_dict((snapshots))
        path = f"atlite_download_{snapshot_dict['start']}_{snapshot_dict['periods']}_{snapshot_dict['frequency']}_{self.lat}_{self.lon}"
        cutout = atlite.Cutout(path)
        return cutout.prepare()
