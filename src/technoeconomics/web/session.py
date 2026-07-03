"""User session management."""

from __future__ import annotations

import asyncio
import enum
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from anyio import (
    CapacityLimiter,
    create_memory_object_stream,
    from_thread,
    to_thread,
)
from cachetools import TTLCache
from fastapi.sse import ServerSentEvent

from technoeconomics import progress
from technoeconomics.backend.solve import solve as _solve

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from anyio.streams.memory import (
        MemoryObjectReceiveStream,
        MemoryObjectSendStream,
    )

    from technoeconomics.backend.preset import Preset
    from technoeconomics.model.plant import Plant

log = logging.getLogger(__name__)

# Cap concurrent solves across all sessions within AnyIO's shared thread pool.
_solves = CapacityLimiter(8)


class SolveStatus(enum.StrEnum):
    """Solve state machine."""

    IDLE = "idle"
    SOLVING = "solving"
    DONE = "done"
    FAILED = "failed"


class Session:
    """Server-side state for one user, addressed by an opaque cookie id.

    When a user connects they are assigned an id via a cookie. Sessions
    are managed to enable future optimisations via reuse of model state
    between runs.

    Args:
        id: The opaque session id (the cookie value).
        plant: The plant the session starts from.
    """

    def __init__(self, id: str, plant: Plant) -> None:
        self.id = id
        self.plant = plant
        self.status = SolveStatus.IDLE
        # One bounded stream per session: the solve worker sends progress, `events` drains it.
        self._send: MemoryObjectSendStream[ServerSentEvent]
        self._receive: MemoryObjectReceiveStream[ServerSentEvent]
        self._send, self._receive = create_memory_object_stream[ServerSentEvent](256)
        self._task: asyncio.Task[None] | None = None  # retain the in-flight solve task

    def launch(self, plant: Plant, preset: Preset) -> None:
        """Launch a solve in the background and return at once.

        Ignored while a solve is already in flight -- one per session; the check runs on the
        single-threaded event loop, so no lock is needed. The blocking solver runs in a worker
        thread (`to_thread.run_sync` is itself a coroutine, so we schedule it directly) to keep
        the loop free. The task is retained (the loop only weakly references running tasks) and
        abandoned on cancellation, since a worker thread can't be interrupted mid-solve.

        Args:
            plant: The plant to solve (passed by value, so a later edit to `self.plant`
                cannot change what an in-flight solve is computing).
            preset: The preset supplying which numbers and plots to compute.
        """
        if self._task is not None and not self._task.done():
            return
        self.status = SolveStatus.SOLVING
        self._task = asyncio.create_task(
            to_thread.run_sync(
                self._run_solve, plant, preset, abandon_on_cancel=True, limiter=_solves
            )
        )

    def _run_solve(self, plant: Plant, preset: Preset) -> None:
        """Solve in a worker thread, pushing the numbers, charts, and a terminal event.

        Args:
            plant: The plant to solve.
            preset: The preset supplying which numbers and plots to compute.
        """
        try:
            with progress.sink(self._message):
                result = _solve(plant, preset)
            self._push(ServerSentEvent(event="numbers", data=result["numbers"]))
            for chart in result["plots"]:
                self._push(ServerSentEvent(event="chart", data=chart))
            self._push(ServerSentEvent(event="done", raw_data=""))
            self.status = SolveStatus.DONE
        except Exception as exc:  # noqa: BLE001 -- surface any solve failure to the user
            log.exception("Solve failed")
            self.status = SolveStatus.FAILED
            self._push(ServerSentEvent(event="failed", raw_data=str(exc)))

    def _push(self, event: ServerSentEvent) -> None:
        """Hand a progress event to the loop's send stream, dropping it if it can't be sent.

        Called from the solve worker thread, so it hops to the event loop via `from_thread` to
        touch the (not thread-safe) memory stream. It never blocks: `send_nowait` raises rather
        than awaits, and a full buffer (`WouldBlock`) or a closed stream just drops the
        event -- progress is best-effort.

        Args:
            event: The event to enqueue for the page.
        """
        try:
            from_thread.run_sync(self._send.send_nowait, event)
        except Exception:  # noqa: BLE001 -- WouldBlock/closed/loop gone: progress is best-effort
            pass

    def _message(self, text: str) -> None:
        """Stream one progress line to the page (and log it), as the solve's `progress` sink.

        Bound via [`progress.sink`][technoeconomics.progress.sink] around the solve, so a
        `progress.emit` anywhere in the solve stack lands here; runs on the worker thread.

        Args:
            text: The progress line to show on the page's run console.
        """
        log.info(text)
        self._push(ServerSentEvent(event="progress", raw_data=text))

    def report(self, event: ServerSentEvent) -> None:
        """Push an event from the event loop (e.g. a route handler), dropping it if it can't be sent.

        The loop-side counterpart of [`_push`][technoeconomics.web.session.Session._push]: the
        caller is already on the event loop, so it touches the stream directly rather than
        hopping through `from_thread`. Used to surface a ``start``/``failed`` event when a
        request launches (or rejects) a solve.

        Args:
            event: The event to enqueue for the page.
        """
        try:
            self._send.send_nowait(event)
        except Exception:  # noqa: BLE001 -- WouldBlock/closed: progress is best-effort
            pass

    async def events(self) -> AsyncIterator[ServerSentEvent]:
        """Yield this session's progress events for the SSE endpoint to encode.

        An async generator (it holds no thread while idle, so many open streams cost ~nothing)
        that relays each event off the receive stream. It does not close the stream on exit, so
        a client that disconnects and reconnects resumes the same session's progress; the
        stream is closed once, in [`aclose`][technoeconomics.web.session.Session.aclose].

        Yields:
            Each `ServerSentEvent` as it is pushed.
        """
        async for event in self._receive:
            yield event

    async def aclose(self) -> None:
        """Cancel any in-flight solve and close the progress stream.

        Called at application shutdown so a live session leaves behind no worker task. The
        cancelled solve's worker thread keeps running (it cannot be interrupted) but is
        abandoned, its events discarded.
        """
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # the in-flight solve's cancellation, expected
            except Exception:  # noqa: BLE001 -- a failing solve must not block teardown
                log.exception("In-flight solve failed during close")
        self._send.close()  # ends any active `events` stream with end-of-stream


class SessionManager:
    """Holds the live sessions, minting them and letting the cache evict by age and count.

    Eviction needs no special handling: an evicted session is simply dropped, and once no
    request or open stream still references it the interpreter reclaims it on the next
    collection.

    Args:
        maxsize: Maximum number of live sessions before the oldest is evicted.
        ttl: Seconds a session survives without being accessed.
    """

    def __init__(self, *, maxsize: int = 64, ttl: float = 30 * 60):
        self._cache: TTLCache[str, Session] = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, sid: str | None) -> Session | None:
        """Look up a live session by cookie id.

        Args:
            sid: The opaque session id from the cookie, or ``None`` if absent.

        Returns:
            The session, or ``None`` if there is no id or it has expired.
        """
        return self._cache.get(sid) if sid else None

    def create(self, plant: Plant) -> tuple[str, Session]:
        """Mint a fresh session for a plant under a new id.

        Args:
            plant: The plant the session starts from.

        Returns:
            The new session id and the session itself.
        """
        sid = uuid4().hex
        session = Session(id=sid, plant=plant)
        self._cache[sid] = session
        return sid, session

    def get_or_create(
        self, sid: str | None, make_plant: Callable[[], Plant]
    ) -> tuple[str, Session]:
        """Return the live session for `sid`, or mint a new one from `make_plant`.

        Args:
            sid: The opaque session id from the cookie, or ``None`` if absent.
            make_plant: Builds the default plant for a new session; called only when there is
                no live session for `sid`.

        Returns:
            The session id and the session. The id differs from `sid` exactly when a new
            session was minted (so the caller knows to set the cookie).
        """
        if sid is not None:
            session = self._cache.get(sid)
            if session is not None:
                return sid, session
        return self.create(make_plant())

    async def aclose_all(self) -> None:
        """Dispose every live session; call once at application shutdown."""
        for session in list(self._cache.values()):
            await session.aclose()
        self._cache.clear()
