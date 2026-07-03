"""Core data-access contract: the [`Dataset`][technoeconomics.data.Dataset] type and dataset resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Annotated

import pandas as pd
from pydantic import ConfigDict

from technoeconomics.serialise import tagged_codec

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


@dataclass(frozen=True)
class Dataset[T](ABC):
    """Base for all datasets: a lazy, serialisable handle for one value.

    The type parameter ``T`` is the resolved value's type -- ``float`` for a scalar
    dataset, ``pandas.Series`` for a series. Concrete datasets are frozen dataclasses
    subclassing ``Dataset[float]`` or ``Dataset[pd.Series]`` and implementing ``compute``.

    (De)serialisation is declared once, on the [`ScalarDataset`][technoeconomics.data.ScalarDataset]
    / [`SeriesDataset`][technoeconomics.data.SeriesDataset] aliases, via the class-name-tagged
    codec from [`technoeconomics.serialise`][]; a concrete dataset therefore stays a plain
    pydantic-free ``@dataclass``.
    """

    # Inherited by every dataset: rejects unknown keys when decoding
    # an untrusted share link.
    __pydantic_config__ = ConfigDict(extra="forbid")

    @abstractmethod
    def compute(self, snapshots: pd.DatetimeIndex) -> T:
        """Produce the value, aligned to ``snapshots`` when a series."""


_ds_validate, _ds_dump = tagged_codec(Dataset)
type ScalarDataset = Annotated[Dataset[float], _ds_validate, _ds_dump]
type SeriesDataset = Annotated[Dataset[pd.Series], _ds_validate, _ds_dump]


def resolve_datasets[C: DataclassInstance](
    objs: Iterable[C], snapshots: pd.DatetimeIndex
) -> list[C]:
    """Return copies of `objs` with every ``Dataset`` field replaced by its value.

    Args:
        objs: Dataclass instances (typically components) to resolve.
        snapshots: The horizon series values are aligned to.

    Returns:
        New instances with concrete values in place of datasets; instances with no
        dataset fields are returned as is.
    """
    resolved = []
    for obj in objs:
        updates = {
            f.name: value.compute(snapshots)
            for f in fields(obj)
            if isinstance(value := getattr(obj, f.name), Dataset)
        }
        resolved.append(replace(obj, **updates) if updates else obj)
    return resolved
