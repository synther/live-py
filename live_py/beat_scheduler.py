import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Optional, TypeVar

import reactivex
import reactivex.operators
import reactivex.scheduler
from reactivex import abc, typing
from reactivex.disposable import Disposable, SingleAssignmentDisposable
from reactivex.internal.concurrency import default_thread_factory
from reactivex.internal.exceptions import DisposedException
from reactivex.internal.priorityqueue import PriorityQueue
from reactivex.scheduler.periodicscheduler import PeriodicScheduler
from reactivex.scheduler.scheduler import Scheduler

logger = logging.getLogger(__name__)


_TState = TypeVar("_TState")


class BeatScheduledItem(object):
    def __init__(
        self,
        scheduler: Scheduler,
        state: Optional[_TState],
        action: abc.ScheduledAction[_TState],
        duetime_ticks: int,
    ) -> None:
        self.scheduler: Scheduler = scheduler
        self.state: Optional[Any] = state
        self.action: abc.ScheduledAction[_TState] = action
        self.duetime_ticks: int = duetime_ticks
        self.disposable: SingleAssignmentDisposable = SingleAssignmentDisposable()

    def invoke(self) -> None:
        ret = self.scheduler.invoke_action(self.action, state=self.state)
        self.disposable.disposable = ret

    def cancel(self) -> None:
        """Cancels the work item by disposing the resource returned by
        invoke_core as soon as possible."""

        self.disposable.dispose()

    def is_cancelled(self) -> bool:
        return self.disposable.is_disposed

    def __lt__(self, other: "BeatScheduledItem") -> bool:
        return self.duetime_ticks < other.duetime_ticks

    def __gt__(self, other: "BeatScheduledItem") -> bool:
        return self.duetime_ticks > other.duetime_ticks

    def __eq__(self, other: Any) -> bool:
        try:
            return self.duetime_ticks == other.duetime_ticks
        except AttributeError:
            return NotImplemented


ticks_per_beat = 1000  # about 0.5 ms tick resolution


def bpm_to_tick_duration_usec(bpm: float) -> int:
    beat_duration_usec = 60 * 1000000 / bpm
    return int(beat_duration_usec / ticks_per_beat)


def now_world_usec() -> int:
    return int(time.monotonic() * 1000000)


class BeatScheduler(PeriodicScheduler, abc.DisposableBase):
    """Creates an object that schedules units of work on a designated thread."""

    def __init__(
        self,
        thread_factory: Optional[typing.StartableFactory] = None,
        exit_if_empty: bool = False,
    ) -> None:
        super().__init__()
        self._is_disposed = False

        self._thread_factory: typing.StartableFactory = (
            thread_factory or default_thread_factory
        )

        self._thread: Optional[typing.Startable] = None
        self._condition = threading.Condition(threading.Lock())
        self._queue: PriorityQueue[BeatScheduledItem] = PriorityQueue()
        self._ready_list: Deque[BeatScheduledItem] = deque()

        self._exit_if_empty = exit_if_empty

        self._tick_duration_usec = bpm_to_tick_duration_usec(120)
        self._last_tick_duration_change_usec = now_world_usec()
        self._ticks_on_last_tick_duration_change = 0.0

    @property
    def now(self) -> int:
        """
        In ticks
        """

        ticks_passed_from_last_tick_duration_change = (
            now_world_usec() - self._last_tick_duration_change_usec
        ) / self._tick_duration_usec

        return int(ticks_passed_from_last_tick_duration_change + self._ticks_on_last_tick_duration_change)

    @classmethod
    def to_timedelta(cls, value: int) -> int:
        return value

    def change_ticks_resolution_bpm(self, bpm: float):
        logger.debug(f"Change bpm to {bpm}")

        # TODO make it atomic
        # TODO protect multithreading
        with self._condition:
            self._ticks_on_last_tick_duration_change = self.now
            self._tick_duration_usec = bpm_to_tick_duration_usec(bpm)
            self._last_tick_duration_change_usec = now_world_usec()

            self._condition.notify()

        logger.debug(
            f"{self._ticks_on_last_tick_duration_change=} {self._tick_duration_usec=} {self._last_tick_duration_change_usec=}")

    def schedule(
        self, action: typing.ScheduledAction[_TState], state: Optional[_TState] = None
    ) -> abc.DisposableBase:
        """Schedules an action to be executed.

        Args:
            action: Action to be executed.
            state: [Optional] state to be given to the action function.

        Returns:
            The disposable object used to cancel the scheduled action
            (best effort).
        """

        return self.schedule_absolute(self.now, action, state=state)

    def schedule_relative(
        self,
        duetime: int,
        action: typing.ScheduledAction[_TState],
        state: Optional[_TState] = None,
    ) -> abc.DisposableBase:
        """Schedules an action to be executed after duetime.

        Args:
            duetime: Relative time after which to execute the action.
            action: Action to be executed.
            state: [Optional] state to be given to the action function.

        Returns:
            The disposable object used to cancel the scheduled action
            (best effort).
        """

        return self.schedule_absolute(self.now + duetime, action, state)

    def schedule_absolute(
        self,
        duetime_ticks: int,
        action: typing.ScheduledAction[_TState],
        state: Optional[_TState] = None,
    ) -> abc.DisposableBase:
        """Schedules an action to be executed at duetime.

        Args:
            duetime: Absolute time at which to execute the action.
            action: Action to be executed.
            state: [Optional] state to be given to the action function.

        Returns:
            The disposable object used to cancel the scheduled action
            (best effort).
        """

        if self._is_disposed:
            raise DisposedException()

        dt = duetime_ticks
        si: BeatScheduledItem = BeatScheduledItem(self, state, action, dt)

        with self._condition:
            if dt <= self.now:
                self._ready_list.append(si)
            else:
                self._queue.enqueue(si)
            self._condition.notify()  # signal that a new item is available
            self._ensure_thread()

        return Disposable(si.cancel)

    def schedule_periodic(
        self,
        period: typing.RelativeTime,
        action: typing.ScheduledPeriodicAction[_TState],
        state: Optional[_TState] = None,
    ) -> abc.DisposableBase:
        """Schedules a periodic piece of work.

        Args:
            period: Period in seconds or timedelta for running the
                work periodically.
            action: Action to be executed.
            state: [Optional] Initial state passed to the action upon
                the first iteration.

        Returns:
            The disposable object used to cancel the scheduled
            recurring action (best effort).
        """

        if self._is_disposed:
            raise DisposedException()

        return super().schedule_periodic(period, action, state=state)

    def _has_thread(self) -> bool:
        """Checks if there is an event loop thread running."""
        with self._condition:
            return not self._is_disposed and self._thread is not None

    def _ensure_thread(self) -> None:
        """Ensures there is an event loop thread running. Should be
        called under the gate."""

        if not self._thread:
            thread = self._thread_factory(self.run)
            self._thread = thread
            thread.start()

    def run(self) -> None:
        """Event loop scheduled on the designated event loop thread.
        The loop is suspended/resumed using the condition which gets notified
        by calls to Schedule or calls to dispose."""

        ready: Deque[BeatScheduledItem] = deque()

        while True:

            with self._condition:

                # The notification could be because of a call to dispose. This
                # takes precedence over everything else: We'll exit the loop
                # immediately. Subsequent calls to Schedule won't ever create a
                # new thread.
                if self._is_disposed:
                    return

                # Sort the ready_list (from recent calls for immediate schedule)
                # and the due subset of previously queued items.
                time_ticks = self.now
                while self._queue:
                    due_ticks = self._queue.peek().duetime_ticks
                    while self._ready_list and due_ticks > self._ready_list[0].duetime_ticks:
                        ready.append(self._ready_list.popleft())
                    if due_ticks > time_ticks:
                        break
                    ready.append(self._queue.dequeue())
                while self._ready_list:
                    ready.append(self._ready_list.popleft())

            # Execute the gathered actions
            while ready:
                item = ready.popleft()
                if not item.is_cancelled():
                    item.invoke()

            # Wait for next cycle, or if we're done let's exit if so configured
            with self._condition:

                if self._ready_list:
                    continue

                elif self._queue:
                    time_ticks = self.now
                    item = self._queue.peek()
                    seconds = (item.duetime_ticks - time_ticks) * self._tick_duration_usec / 1000000
                    if seconds > 0:
                        logger.debug("timeout: %s", seconds)
                        self._condition.wait(seconds)

                elif self._exit_if_empty:
                    self._thread = None
                    return

                else:
                    self._condition.wait()

    def dispose(self) -> None:
        """Ends the thread associated with this scheduler. All
        remaining work in the scheduler queue is abandoned.
        """

        with self._condition:
            if not self._is_disposed:
                self._is_disposed = True
                self._condition.notify()


def beats(beats: float) -> int:
    """To ticks
    """

    return int(beats * ticks_per_beat)


if __name__ == '__main__':
    import coloredlogs
    logging.basicConfig(level=logging.DEBUG)

    coloredlogs.install(level='DEBUG',
                        fmt='%(asctime)s,%(msecs)03d %(name)22s %(levelname)5s %(message)s')

    sch = BeatScheduler()

    logger.debug("before subscribe")

    reactivex.of(1).pipe(
        reactivex.operators.map(lambda v: reactivex.of(v + 10).pipe(
            reactivex.operators.delay(beats(1)))
        ),
        reactivex.operators.flat_map(lambda v: v),
        reactivex.operators.while_do(lambda x: True)
    ).subscribe(
        on_next=lambda x: logger.debug(f"x = {x}"),
        scheduler=sch)

    logger.debug("after subscribe")

    time.sleep(0.75)
    sch.change_ticks_resolution_bpm(240)

    time.sleep(5)
