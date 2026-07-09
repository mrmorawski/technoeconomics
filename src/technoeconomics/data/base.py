"""Core data-access contract: the [`Dataset`][technoeconomics.data.Dataset] type and dataset resolution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, fields, replace
from threading import Lock
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import pandas as pd
from cachetools import TTLCache
from pydantic import ConfigDict

from technoeconomics.serialise import _snapshots_to_dict, tagged_codec

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

    # Opt-in result memoisation. A subclass sets ``cache = True`` when its ``compute`` is a
    # pure, deterministic function of its (hashable) fields and ``snapshots`` and worth not
    # repeating -- a weather download, say. Off by default: recompute-always is the safe
    # choice, so turning it on is the author's promise that the value never goes stale.
    cache: ClassVar[bool] = False

    @abstractmethod
    def compute(self, snapshots: pd.DatetimeIndex) -> T:
        """Produce the value, aligned to ``snapshots`` when a series."""

    def resolve(self, snapshots: pd.DatetimeIndex) -> T:
        """Return this dataset's value over ``snapshots``, memoised when ``cache`` is set.

        The resolution entry point, wrapping the author's
        [`compute`][technoeconomics.data.Dataset.compute]:
        [`resolve_datasets`][technoeconomics.data.resolve_datasets] calls it. When ``cache``
        is ``True`` the value is keyed by ``(self, snapshots)`` -- a frozen dataset with
        hashable fields is its own key -- and computed once even under concurrent resolves;
        otherwise ``compute`` runs every time.

        Args:
            snapshots: The horizon the value is aligned to.

        Returns:
            The computed value. A cached value is shared by reference, so callers must treat
            it as read-only (resolution copies it into a component rather than mutating it).
        """
        if not self.cache:
            return self.compute(snapshots)
        return _RESULTS.get_or_make(
            (self, _snapshots_key(snapshots)), lambda: self.compute(snapshots)
        )


_ds_validate, _ds_dump = tagged_codec(Dataset)
type ScalarDataset = Annotated[Dataset[float], _ds_validate, _ds_dump]
type SeriesDataset = Annotated[Dataset[pd.Series], _ds_validate, _ds_dump]


# A dataset opts in only when its value is a pure function of (fields, snapshots), so a
# cached value never goes stale: the TTL is a memory bound, not a freshness one, and can be
# generous. Holds 256 distinct (dataset, horizon) pairs, each until six hours idle.
_MAXSIZE = 256
_TTL_SECONDS = 6 * 60 * 60


class ResultCache:
    """Process-wide single-flight memoiser: one factory call per key, shared by racers.

    A dataset resolved concurrently across the solve worker threads must compute once, not
    once per thread. The first caller to miss stores a `Future` under the key and runs the
    factory; callers arriving while it is in flight find that `Future` and block on its
    result. The lock guards only the `TTLCache` bookkeeping -- which is not thread-safe, and
    mutates even on a read here to refresh the idle timer -- while the factory runs unlocked,
    so a slow compute never blocks a hit or an unrelated key.

    Args:
        maxsize: Distinct keys retained before the least-recently-used is evicted.
        ttl: Seconds a key survives untouched (each hit resets the timer).
    """

    def __init__(self, maxsize: int = _MAXSIZE, ttl: float = _TTL_SECONDS) -> None:
        self._cache: TTLCache[Hashable, Future[Any]] = TTLCache(
            maxsize=maxsize, ttl=ttl
        )
        self._lock = Lock()

    def get_or_make[T](self, key: Hashable, factory: Callable[[], T]) -> T:
        """Return the value for `key`, computing it via `factory` on a miss.

        Args:
            key: A hashable key that fully determines the value.
            factory: Produces the value on a miss; called at most once per in-flight key.

        Returns:
            The value for `key`, freshly computed or replayed from an in-flight or earlier
            call. A `factory` that raises propagates to every waiter and is not cached, so a
            later call retries.
        """
        with self._lock:
            future = self._cache.get(key)
            if future is not None:
                self._cache[key] = future  # re-insert to refresh the idle TTL
                mine = False
            else:
                future = self._cache[key] = Future()
                mine = True
        if mine:
            try:
                future.set_result(factory())
            except Exception as exc:  # noqa: BLE001 -- re-raised to every waiter below
                with self._lock:
                    # Drop only if still ours; a refresh/eviction may have replaced it.
                    if self._cache.get(key) is future:
                        del self._cache[key]
                future.set_exception(exc)
        return future.result()


# Shared by every dataset that opts into caching; keyed by (dataset, snapshots) in `resolve`.
_RESULTS = ResultCache()


def _snapshots_key(snapshots: pd.DatetimeIndex) -> Hashable:
    """A hashable, canonical key for a snapshot horizon (a `DatetimeIndex` is unhashable).

    Reuses the compact serialisation encoding, freezing its explicit-values list (an
    irregular index has no ``freq``) to a tuple so the whole key is hashable.
    """
    encoded = _snapshots_to_dict(snapshots)
    return tuple(
        (k, tuple(v) if isinstance(v, list) else v) for k, v in sorted(encoded.items())
    )


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
            f.name: value.resolve(snapshots)
            for f in fields(obj)
            if isinstance(value := getattr(obj, f.name), Dataset)
        }
        resolved.append(replace(obj, **updates) if updates else obj)
    return resolved
