"""A tiny progress channel: components emit lines, the caller decides where they go.

Neutral and low-level -- it imports nothing from `web`/`backend`/`model`, so any layer (the
solver here, and later dataset retrieval deep in the model) can `emit` a progress line without
knowing who, if anyone, is listening. A listener is a *sink* bound around some work with
[`sink`][technoeconomics.progress.sink]; a web run binds one that streams to the page
for the duration of a solve. With no sink bound -- the CLI, tests -- `emit` is a no-op.

The sink lives in a `ContextVar`, so `emit` anywhere in the dynamic scope of the `sink(...)`
block reaches it -- including deep inside a synchronous call tree like `build_network`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_sink: ContextVar[Callable[[str], None] | None] = ContextVar(
    "progress_sink", default=None
)


def emit(text: str) -> None:
    """Report a progress line to the bound sink, if any.

    A no-op when no sink is bound, so callers can emit unconditionally.

    Args:
        text: The human-readable progress line (e.g. ``"Building network…"``).
    """
    sink = _sink.get()
    if sink is not None:
        sink(text)


@contextmanager
def sink(fn: Callable[[str], None]) -> Iterator[None]:
    """Bind `fn` as the progress sink for the duration of the ``with`` block.

    Args:
        fn: Receives each emitted progress line.

    Yields:
        Nothing; the sink is bound until the block exits.
    """
    token = _sink.set(fn)
    try:
        yield
    finally:
        _sink.reset(token)
