"""Data access: lazy, serialisable datasets resolved to scalars or series."""

from technoeconomics.data.base import (
    Dataset,
    ScalarDataset,
    SeriesDataset,
    resolve_datasets,
)
from technoeconomics.data.sources import Constant, Sinusoidal
from technoeconomics.serialise import Scalar, Timeseries

__all__ = [
    "Constant",
    "Dataset",
    "Scalar",
    "ScalarDataset",
    "SeriesDataset",
    "Sinusoidal",
    "Timeseries",
    "resolve_datasets",
]
