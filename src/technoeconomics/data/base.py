"""Core data-access contract: the [`Dataset`][technoeconomics.data.Dataset] type and dataset resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields, replace
from functools import cache
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from pydantic import TypeAdapter

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
    subclassing ``Dataset[float]`` or ``Dataset[pd.Series]`` and implementing ``compute``.

    Serialisation is inherited and needs no per-class code, and mirrors the other model types:
    ``to_dict`` tags the dict with the class name and writes the fields (a trusted in-memory
    object needs only structural encoding); ``from_dict`` rebuilds the named subclass and
    *validates* the fields via a pydantic [`TypeAdapter`][] (decode is untrusted input, encode
    is not). A concrete dataset therefore stays a pydantic-free ``@dataclass``.
    """

    @abstractmethod
    def compute(self, snapshots: pd.DatetimeIndex) -> T:
        """Produce the value, aligned to ``snapshots`` when a series.

        Where the (possibly slow) backend work happens. A dataset that is expensive
        to compute is responsible for its own caching (e.g. atlite caches its cutout
        on disk); the framework does not cache.
        """

    def to_dict(self) -> dict:
        """Serialise to a tagged dict; round-trips through `from_dict`."""
        return {
            "__dataset__": type(self).__name__,
            **type_adapter(type(self)).dump_python(self, mode="json"),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Dataset:
        """Reconstruct a dataset from `to_dict` output.

        The class name tag selects which subclass to rebuild; its pydantic `TypeAdapter` then
        validates the fields, so a bad value from an untrusted share link (e.g. a string in a
        numeric field, or a missing field) is rejected here rather than failing later.

        Args:
            d: A dict produced by [`to_dict`][technoeconomics.data.Dataset.to_dict].

        Returns:
            The reconstructed dataset.

        Raises:
            ValueError: If `d` is not a known dataset, or a field is invalid. (pydantic's
                `ValidationError`, raised for a bad field, is itself a `ValueError`.)
        """
        if not isinstance(d, dict):
            raise ValueError("dataset must be an object")
        name = d.get("__dataset__")
        registry = concrete_subclasses(Dataset)
        if name not in registry:
            raise ValueError(f"unknown dataset type: {name!r}")
        payload = {k: v for k, v in d.items() if k != "__dataset__"}
        return type_adapter(registry[name]).validate_python(payload)


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


@cache
def type_adapter(cls: type) -> TypeAdapter[Any]:
    """A cached pydantic validator/serialiser for one model class.

    Built from the class's dataclass fields, so model classes (datasets, components, buses)
    stay plain pydantic-free ``@dataclass``es while gaining declarative field validation and
    JSON (de)serialisation. Cached because building a `TypeAdapter` compiles a validator, and
    there are few classes.

    Args:
        cls: The concrete dataclass to (de)serialise.

    Returns:
        A `TypeAdapter` for `cls`.
    """
    return TypeAdapter(cls)
