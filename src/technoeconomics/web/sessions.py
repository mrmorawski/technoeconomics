"""Session and worker management for optimisation runs.

Solve jobs take up to a few minutes, so the server runs them in worker threads (pypsa
and HiGHS block; running them on the event loop would freeze every user).

State is managed by a [Session][technoeconomics.backend.sessions.Session]. We maintain it
to reuse solver artifacts between runs, enabling faster solve times and making the website
more interactive. The user can change a parameter value, click solve, and the solution
updates within seconds.

We use AnyIO to create the workers and tap into the main FastAPI event loop, so that we
can stream intermediate results such as logs from the solve job to the frontend.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from anyio import (
    CapacityLimiter,
    create_memory_object_stream,
    create_task_group,
    from_thread,
    to_thread,
)
from cachetools import TTLCache

from technoeconomics.backend.solve import solve

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyio.streams.memory import MemoryObjectSendStream

    from technoeconomics.backend.preset import Preset
    from technoeconomics.model.plant import Plant

log = logging.getLogger(__name__)

# An event streamed to the page: (kind, payload). kind is one of
# "log" | "numbers" | "chart" | "done" | "error".
Event = tuple[str, object]


@dataclass
class Session:
    """Server-side state for one user, kept in memory and addressed by cookie id.

    Attributes:
        plant: The user's current plant -- the source of truth edits are applied to.
        result: The last ``{"numbers", "plots"}`` produced, for re-render and sharing.
    """

    plant: Plant
    result: dict | None = None


_sessions: TTLCache = TTLCache(
    maxsize=64, ttl=30 * 60
)  # sid -> Session; library evicts
_solves = CapacityLimiter(8)  # cap concurrent solves within AnyIO's shared thread pool
# The active worker thread's stream, so the log handler knows where to forward records
# without being passed it. Set in _solve_to_stream, read in _Capture.emit.
_sink: ContextVar[MemoryObjectSendStream[Event] | None] = ContextVar(
    "sink", default=None
)


def get(sid: str | None) -> Session | None:
    """Look up a session by cookie id.

    Args:
        sid: The opaque session id from the cookie, or ``None`` if absent.

    Returns:
        The session, or ``None`` if there is no id or it has expired.
    """
    return _sessions.get(sid) if sid else None


def create(plant: Plant) -> tuple[str, Session]:
    """Create a fresh session for a plant and register it under a new id.

    Args:
        plant: The plant the session starts from.

    Returns:
        The new session id and the session itself.
    """
    sid = uuid4().hex
    session = Session(plant=plant)
    _sessions[sid] = session
    return sid, session


async def stream_solve(session: Session, preset: Preset) -> AsyncIterator[Event]:
    """Solve the session's plant in a worker thread, yielding events as they arise.

    The solve runs in an AnyIO worker thread (off the event loop) and pushes its log
    lines and results back through an in-memory stream, which this generator drains.
    The task group scopes the worker to this call: when the client disconnects and the
    generator is closed, the worker is awaited and cleaned up.

    Args:
        session: The session whose plant to solve.
        preset: The preset supplying which numbers and plots to compute.

    Yields:
        ``(kind, payload)`` events, terminating after a ``done`` or ``error``.
    """
    send, receive = create_memory_object_stream[Event](256)
    async with create_task_group() as tg:
        tg.start_soon(_run_solve, session, preset, send)
        async with receive:
            async for event in receive:
                yield event
                if event[0] in ("done", "error"):
                    break
        tg.cancel_scope.cancel()


async def _run_solve(
    session: Session, preset: Preset, send: MemoryObjectSendStream[Event]
) -> None:
    """Run the blocking solve in a worker thread, closing the stream when it ends.

    Args:
        session: The session whose plant to solve.
        preset: The preset supplying which numbers and plots to compute.
        send: The stream the worker pushes events onto; closed here so the consumer's
            iteration terminates.
    """
    try:
        await to_thread.run_sync(
            _solve_to_stream, session, preset, send, limiter=_solves
        )
    finally:
        send.close()


def _solve_to_stream(
    session: Session, preset: Preset, send: MemoryObjectSendStream[Event]
) -> None:
    """Worker-thread body: solve, then push results (and, via `_sink`, logs) to `send`.

    Runs off the event loop, so it hands every event back with `from_thread`. Any failure
    becomes an ``error`` event rather than propagating, so the stream always terminates.

    Args:
        session: The session being solved; its `result` is updated on success.
        preset: The preset supplying which numbers and plots to compute.
        send: The stream to push events onto.
    """

    def push(kind: str, payload: object) -> None:
        from_thread.run_sync(send.send_nowait, (kind, payload))

    token = _sink.set(send)
    try:
        result = solve(session.plant, preset)
        session.result = result
        push("numbers", result["numbers"])
        for chart in result["plots"]:
            push("chart", chart)
        push("done", "")
    except Exception as exc:  # noqa: BLE001 -- surface any solve failure to the user
        log.exception("Solve failed")
        push("error", str(exc))
    finally:
        _sink.reset(token)


class _Capture(logging.Handler):
    """Forwards a worker thread's log records to its solve stream as ``log`` events."""

    def emit(self, record: logging.LogRecord) -> None:
        """Push the record's message onto the active solve stream, if any.

        Args:
            record: The log record emitted on the current (worker) thread.
        """
        send = _sink.get()
        if send is None:
            return
        try:
            from_thread.run_sync(send.send_nowait, ("log", record.getMessage()))
        except Exception:  # noqa: BLE001 -- a log line must never break the solve
            pass


logging.getLogger("technoeconomics").addHandler(_Capture())
