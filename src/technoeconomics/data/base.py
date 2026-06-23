"""Core data-access contract: the `Dataset` type and dataset resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

# The eager 1-D value types a series field accepts as a literal. No single stdlib
# type covers these: ``collections.abc.Sequence`` excludes numpy/pandas, and
# ``numpy.typing.ArrayLike`` is far too broad (scalars, nested sequences). So we spell
# out the three that matter. ``Sequence[float]`` covers list and tuple; a pandas
# Series, if passed, must be indexed by the snapshots (PyPSA rejects misaligned ones).
type Timeseries = np.ndarray | pd.Series | Sequence[float]


@dataclass(frozen=True)
class Dataset[T](ABC):
    """Base for all datasets: a lazy, serialisable handle for one value.

    The type parameter ``T`` is the resolved value's type -- ``float`` for a scalar
    dataset, ``pandas.Series`` for a series. Concrete datasets are frozen dataclasses
    subclassing ``Dataset[float]`` or ``Dataset[pd.Series]`` and implementing
    ``compute``; they inherit serialisation (``to_dict``/``from_dict``) for free.
    """

    @abstractmethod
    def compute(self, snapshots: pd.DatetimeIndex) -> T:
        """Produce the value, aligned to ``snapshots`` when a series.

        Where the (possibly slow) backend work happens. A dataset that is expensive
        to compute is responsible for its own caching (e.g. atlite caches its cutout
        on disk); the framework does not cache.
        """

    def to_dict(self) -> dict:
        """Serialise to a tagged dict; nested datasets serialise recursively."""
        out: dict = {"__dataset__": type(self).__name__}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = v.to_dict() if isinstance(v, Dataset) else v
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Dataset:
        """Reconstruct a dataset (and any nested datasets) from `to_dict` output."""
        target = concrete_subclasses(Dataset)[d["__dataset__"]]
        kwargs = {
            k: (Dataset.from_dict(v) if _is_dataset_dict(v) else v)
            for k, v in d.items()
            if k != "__dataset__"
        }
        return target(**kwargs)


type ScalarDataset = Dataset[float]
type SeriesDataset = Dataset[pd.Series]


def resolve_datasets[C: DataclassInstance](
    objs: Iterable[C], snapshots: pd.DatetimeIndex
) -> list[C]:
    """Return copies of `objs` with every ``Dataset`` field replaced by its value.

    Args:
        objs: Dataclass instances (typically components) to resolve.
        snapshots: The horizon series values are aligned to.

    Returns:
        New instances with concrete values in place of datasets.
    """
    return [_resolved(o, snapshots) for o in objs]


def concrete_subclasses(base: type) -> dict[str, type]:
    """Map class name -> every (recursive) subclass of ``base`` (for type-tag lookup)."""
    found: dict[str, type] = {}
    for cls in base.__subclasses__():
        found[cls.__name__] = cls
        found.update(concrete_subclasses(cls))
    return found


def _resolved[C: DataclassInstance](obj: C, snapshots: pd.DatetimeIndex) -> C:
    """Return a copy of one dataclass instance with its dataset fields resolved."""
    updates = {
        f.name: value.compute(snapshots)
        for f in fields(obj)
        if isinstance(value := getattr(obj, f.name), Dataset)
    }
    return replace(obj, **updates) if updates else obj


def _is_dataset_dict(v: object) -> bool:
    """Whether a serialised value represents a (nested) dataset."""
    return isinstance(v, dict) and "__dataset__" in v
