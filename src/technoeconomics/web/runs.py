"""Runs: launch a solve, stream its progress, store its result -- addressed by run_id.

Replaces the cookie-keyed `Session`. A `Run` is addressable by an opaque run_id; there are no
user sessions and no cross-run history. Results are a **GET-able resource** stored on the run,
and the SSE stream is **progress-only**: it carries progress lines and one terminal
``done``/``failed`` poke, after which the server closes the stream and the client GETs the
result (no reconnect-into-404 loop).

The lifecycle invariants that keep this correct, each small but load-bearing:

- **Task pinning.** The event loop holds a running task only weakly and the completed-run cache
  is evictable, so a running solve's task is pinned in a manager-level set until it finishes --
  otherwise an eviction mid-solve could silently drop it.
- **Result before terminal event.** The result is stored on the run *before* the terminal SSE
  event is emitted, so a client's ``done`` -> GET can never race an empty run.
- **TTL from completion.** A running run is pinned (never evicted); on completion it moves into
  a bounded `TTLCache` whose clock starts at completion, so a long run cannot expire from under
  its own reconnect, and completed-run memory (which holds full chart payloads) stays bounded.
- **Reconnect replay.** Progress events carry monotonic ids; on reconnect the browser sends
  ``Last-Event-ID`` and the run replays only newer events, so the console is not duplicated.
- **Watchdog.** A wedged solve is marked ``failed`` after a deadline so its accounting frees up.
  The worker thread and its `CapacityLimiter` slot are unrecoverable (threads can't be
  interrupted) but the user is not locked out until restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal
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

    from anyio.streams.memory import MemoryObjectSendStream

    from technoeconomics.backend.preset import Preset
    from technoeconomics.model.plant import Plant

log = logging.getLogger(__name__)

# Cap concurrent solves across all runs within AnyIO's shared thread pool.
_solves = CapacityLimiter(8)
# Progress tail kept per run; the terminal event must survive a chatty run's replay window.
_TAIL_CAP = 512
# Per-subscriber SSE queue depth.
_BUFFER = 256

Status = Literal["running", "done", "failed"]
_TERMINAL = ("done", "failed")


class Run:
    """One solve, addressed by `id`: its status, result, progress tail, and live subscribers.

    Args:
        id: The opaque run id.
        manager: The owning `RunManager`, told when this run reaches a terminal state so it can
            move the run from the live pin into the completed-run TTL cache.
    """

    def __init__(self, id: str, manager: RunManager) -> None:
        self.id = id
        self._manager = manager
        self.status: Status = "running"
        self.result: dict | None = None  # {"numbers", "charts"} once done
        self.error: str | None = None
        self._events: list[ServerSentEvent] = []  # progress tail, monotonically id'd
        self._next_event_id = 1
        self._subscribers: set[MemoryObjectSendStream[ServerSentEvent]] = set()
        self._task: asyncio.Task[None] | None = (
            None  # the run coroutine (pinned by manager)
        )

    def snapshot(self) -> dict:
        """The run's current state for ``GET /api/runs/{id}``.

        Returns:
            ``{"status": ...}`` plus ``error`` when failed or ``results`` when done.
        """
        state: dict = {"status": self.status}
        if self.status == "failed":
            state["error"] = self.error
        elif self.status == "done":
            state["results"] = self.result
        return state

    async def _run(self, plant: Plant, preset: Preset, deadline: float) -> None:
        """Run the solve in a worker thread under a deadline; the task body.

        The blocking solver runs in a worker thread (abandoned, not interrupted, on cancel).
        `_run_solve` marks the run terminal from inside the thread; this coroutine only has to
        catch the two cases the thread cannot report itself -- the watchdog deadline and an
        unexpected failure in the await machinery.
        """
        try:
            async with asyncio.timeout(deadline):
                await to_thread.run_sync(
                    self._run_solve,
                    plant,
                    preset,
                    abandon_on_cancel=True,
                    limiter=_solves,
                )
        except TimeoutError:
            log.warning("Run %s exceeded %.0fs; marking failed", self.id, deadline)
            self._finish("failed", error="solve timed out")
        except Exception:  # noqa: BLE001 -- a crash here must still terminate the run
            log.exception("Run %s crashed", self.id)
            self._finish("failed", error="internal error")

    def _run_solve(self, plant: Plant, preset: Preset) -> None:
        """Solve in a worker thread, then mark the run terminal (result stored first).

        Runs on the worker thread; hops to the loop for every state change via `_on_loop`.
        """
        try:
            with progress.sink(self._message):
                out = _solve(plant, preset)
            result = {"numbers": out["numbers"], "charts": out["plots"]}
            self._on_loop(self._finish, "done", result, None)
        except Exception as exc:  # noqa: BLE001 -- surface any solve failure to the user
            log.exception("Solve failed")
            self._on_loop(self._finish, "failed", None, str(exc))

    def _message(self, text: str) -> None:
        """Stream one progress line to subscribers, as the solve's `progress` sink.

        Bound via [`progress.sink`][technoeconomics.progress.sink] around the solve, so a
        `progress.emit` anywhere in the solve stack lands here; runs on the worker thread.
        """
        log.info(text)
        self._on_loop(self._emit, ServerSentEvent(event="progress", raw_data=text))

    def _on_loop(self, fn: Callable[..., None], *args: object) -> None:
        """Run `fn(*args)` on the event loop from the worker thread, dropping it if the loop is gone.

        Progress and completion are best-effort across the thread boundary: at shutdown, or once
        a solve's thread has been abandoned, the loop may be unreachable.
        """
        try:
            from_thread.run_sync(fn, *args)
        except Exception:  # noqa: BLE001 -- loop gone / thread abandoned: best-effort
            pass

    def _emit(self, event: ServerSentEvent) -> None:
        """Assign the event a monotonic id, append it to the tail, and broadcast it (loop-side)."""
        event.id = str(self._next_event_id)
        self._next_event_id += 1
        self._events.append(event)
        del self._events[:-_TAIL_CAP]
        for send in list(self._subscribers):
            try:
                send.send_nowait(event)
            except Exception:  # noqa: BLE001 -- WouldBlock/closed: progress is best-effort
                pass

    def _finish(
        self, status: Status, result: dict | None = None, error: str | None = None
    ) -> None:
        """Mark the run terminal, store its outcome, emit the terminal event, retire it (loop-side).

        Idempotent: the first caller wins, so a watchdog timeout and a late-arriving worker
        result cannot both terminate the run. The result is stored **before** the terminal event
        is emitted, so a subscriber's ``done`` -> GET cannot see an empty run.
        """
        if self.status != "running":
            return
        self.status = status
        self.result = result
        self.error = error
        self._emit(ServerSentEvent(event=status, raw_data=error or ""))
        self._manager.retire(self)

    async def events(self, last_id: int | None) -> AsyncIterator[ServerSentEvent]:
        """Yield this run's events for one SSE connection: replay the tail, then live, then close.

        Registering the subscriber and snapshotting the tail/status happen in one synchronous
        block (no ``await`` between), so -- since emission runs on the same single-threaded loop
        -- an event cannot slip in unseen or be delivered twice. On reconnect the browser's
        ``Last-Event-ID`` becomes `last_id` and only newer tail events replay. The stream ends
        after the terminal event: either it was in the replayed tail (run already finished) or it
        arrives live.

        Args:
            last_id: The last event id the client already has (from ``Last-Event-ID``), or None.

        Yields:
            Each `ServerSentEvent`, replayed then live, up to and including the terminal one.
        """
        send, receive = create_memory_object_stream[ServerSentEvent](_BUFFER)
        self._subscribers.add(send)
        tail = list(self._events)
        already_terminal = self.status != "running"
        try:
            for event in tail:
                if (
                    last_id is not None
                    and event.id is not None
                    and int(event.id) <= last_id
                ):
                    continue
                yield event
            if already_terminal:
                return
            async for event in receive:
                yield event
                if event.event in _TERMINAL:
                    return
        finally:
            self._subscribers.discard(send)
            send.close()

    async def aclose(self) -> None:
        """Cancel the run's task and close all subscriber streams (at application shutdown)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 -- a failing task must not block teardown
                log.exception("Run %s task failed during close", self.id)
        for send in list(self._subscribers):
            send.close()


class RunManager:
    """Holds live and recently-completed runs; launches solves and reaps them.

    A running run is pinned in `_live` and never evicted; on completion it moves to `_done`, a
    bounded `TTLCache` whose clock starts at completion. Tasks are pinned in `_tasks` so a
    running solve is never garbage-collected out from under the loop.

    Args:
        maxsize: Maximum completed runs retained before the least-recently-inserted is evicted.
        ttl: Seconds a completed run survives (covers reconnect and reload-restore).
        deadline: Seconds a solve may run before the watchdog marks it failed.
    """

    def __init__(
        self, *, maxsize: int = 256, ttl: float = 15 * 60, deadline: float = 300
    ) -> None:
        self._live: dict[str, Run] = {}
        self._done: TTLCache[str, Run] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._tasks: set[asyncio.Task[None]] = set()
        self._deadline = deadline

    @property
    def live_count(self) -> int:
        """Number of runs currently solving (for the global live-run cap)."""
        return len(self._live)

    def get(self, run_id: str) -> Run | None:
        """Look up a run by id, whether it is still live or recently completed."""
        return self._live.get(run_id) or self._done.get(run_id)

    def launch(self, plant: Plant, preset: Preset) -> Run:
        """Start solving `plant` in the background and return its `Run` at once.

        Args:
            plant: The plant to solve (already validated and rebuilt from the preset).
            preset: The preset supplying which numbers and plots to compute.

        Returns:
            The new run, pinned live until it reaches a terminal state.
        """
        run = Run(uuid4().hex, self)
        self._live[run.id] = run
        task = asyncio.create_task(run._run(plant, preset, self._deadline))
        run._task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    def retire(self, run: Run) -> None:
        """Move a just-terminal run from the live pin into the completed-run TTL cache (loop-side)."""
        if self._live.pop(run.id, None) is not None:
            self._done[run.id] = run

    async def aclose_all(self) -> None:
        """Cancel every live run and dispose it; call once at application shutdown."""
        for run in list(self._live.values()):
            await run.aclose()
        self._live.clear()
