"""Framework-internal (de)serialisation machinery, collected in one place."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from functools import cache
from typing import Annotated, Any

import numpy as np
import pandas as pd
from pydantic import (
    BeforeValidator,
    InstanceOf,
    PlainSerializer,
    TypeAdapter,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)


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


def concrete_subclasses(base: type) -> dict[str, type]:
    """Map class name -> every (recursive) subclass of ``base`` (for type-tag lookup)."""
    found: dict[str, type] = {}
    for cls in base.__subclasses__():
        found[cls.__name__] = cls
        found.update(concrete_subclasses(cls))
    return found


def tagged_codec(base: type) -> tuple[WrapValidator, PlainSerializer]:
    """Symmetric class-name-tagged (de)serialisation for an open subclass registry.

    The returned pair is attached to an `Annotated` alias of `base`: dumping writes a
    ``{"type": <class name>, ...fields}`` dict, and loading reads that tag to pick the
    concrete subclass and validate its fields. This keeps polymorphic model types (datasets,
    components) as plain dataclasses that gain declarative (de)serialisation from the alias.

    Args:
        base: The registry root whose concrete subclasses are the dispatch targets.

    Returns:
        A ``(WrapValidator, PlainSerializer)`` pair to place in an `Annotated[base, ...]`.
    """

    def dump(v: object) -> dict:
        cls = type(v)
        assert "type" not in {f.name for f in fields(cls)}, (
            f"{cls.__name__} defines a field named 'type', clashing with the type tag"
        )
        return {"type": cls.__name__, **type_adapter(cls).dump_python(v, mode="json")}

    def load(v: object, handler: ValidatorFunctionWrapHandler) -> object:
        if isinstance(v, base):  # in-memory construction path: pass the object through
            return v
        if not isinstance(v, dict):
            raise ValueError(f"{base.__name__.lower()} must be an object")
        payload = dict(v)  # never mutate the caller's dict
        cls = concrete_subclasses(base).get(payload.pop("type", None))
        if cls is None:
            raise ValueError(f"unknown {base.__name__.lower()} type")
        return type_adapter(cls).validate_python(payload)

    return WrapValidator(load), PlainSerializer(dump)


# The eager scalar a parameter accepts as a literal. This is a plain ``float``; the explicit
# serialiser (``float`` coerces ``int`` -> ``float``) is what lets pydantic place it cleanly
# in a union with the dataset/series aliases -- a bare ``float`` branch there serialises an
# ``int`` value with a spurious "unexpected value" warning.
type Scalar = Annotated[float, PlainSerializer(float, return_type=float)]

# The eager 1-D value types a series field accepts as a literal. No single stdlib type
# covers these: ``collections.abc.Sequence`` excludes numpy/pandas, and
# ``numpy.typing.ArrayLike`` is far too broad (scalars, nested sequences). So we spell out
# the three that matter, and serialise any of them to a plain list (index dropped): the
# values are positionally aligned to the snapshots. ``Sequence[float]`` covers list and tuple.
type Timeseries = Annotated[
    np.ndarray | pd.Series | Sequence[float],
    PlainSerializer(lambda v: [float(x) for x in v], return_type=list[float]),
]


def _snapshots_to_dict(index: pd.DatetimeIndex) -> dict:
    """Encode a snapshot index compactly (by freq when regular, else explicit values)."""
    if index.freq is not None:
        return {
            "start": index[0].isoformat(),
            "periods": len(index),
            "freq": index.freqstr,
        }
    return {"values": [t.isoformat() for t in index]}


def _snapshots_from_dict(d: dict) -> pd.DatetimeIndex:
    """Rebuild a snapshot index from `_snapshots_to_dict` output."""
    if "values" in d:
        return pd.DatetimeIndex(d["values"])
    return pd.date_range(start=d["start"], periods=d["periods"], freq=d["freq"])


def _snapshots_from_dict_or_passthrough(v: object) -> pd.DatetimeIndex:
    """Pass a live `DatetimeIndex` through; rebuild one from a `_snapshots_to_dict` dict."""
    if isinstance(v, pd.DatetimeIndex):
        return v
    if isinstance(v, dict):
        return _snapshots_from_dict(v)
    raise ValueError("snapshots must be an object")


type Snapshots = Annotated[
    InstanceOf[pd.DatetimeIndex],
    PlainSerializer(_snapshots_to_dict),
    BeforeValidator(_snapshots_from_dict_or_passthrough),
]
"""A `DatetimeIndex` serialised as a compact ``{start, periods, freq}`` (or explicit values)."""
