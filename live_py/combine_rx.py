from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

from reactivex import Observable, Subject, abc
from reactivex.disposable import (CompositeDisposable,
                                  SingleAssignmentDisposable)

import logging
logger = logging.getLogger(__name__)


def combine_rx(sources: List[Observable[Any]],
               is_rx: List[bool],
               from_: List[Union[str, tuple[str, str]]],
               silent: bool = False,
               ) -> Observable[Tuple[Any, ...]]:
    parent = sources[0]
    assert len(sources) == len(is_rx)

    logger.debug(f'combine_rx: create combine_rx: from {from_}')

    def subscribe(
        observer: abc.ObserverBase[Any], scheduler: Optional[abc.SchedulerBase] = None
    ) -> CompositeDisposable:

        n = len(sources)
        has_value = [False] * n
        first_time_all = True
        is_done = [False] * n
        values = [None] * n

        logger.debug(f'combine_rx: subscribe to combine_rx: from {from_}')

        def _next(i: Any) -> None:
            has_value[i] = True
            nonlocal first_time_all

            if not silent:
                logger.debug(
                    f'combine_rx on_next: values {values}, has_value {has_value}, from {from_}')
                logger.debug(
                    f'                    from "{from_[i]}" = {values[i]} (is_rx={is_rx[i]})')

            if all(has_value):
                if first_time_all or is_rx[i]:
                    if not silent:
                        logger.debug(
                            f'combine_rx: pass to observer {first_time_all=}, {is_rx=}, {values=}')

                    res = tuple(values)
                    first_time_all = False
                    observer.on_next(res)

            elif all([x for j, x in enumerate(is_done) if j != i]):
                observer.on_completed()

        def done(i: Any) -> None:
            is_done[i] = True
            if all(is_done):
                observer.on_completed()

        subscriptions: List[Optional[SingleAssignmentDisposable]] = [None] * n

        def func(i: int) -> None:
            subscriptions[i] = SingleAssignmentDisposable()

            def on_next(x: Any) -> None:
                with parent.lock:
                    values[i] = x
                    _next(i)

            def on_completed() -> None:
                with parent.lock:
                    done(i)

            subscription = subscriptions[i]
            assert subscription
            subscription.disposable = sources[i].subscribe(
                on_next, observer.on_error, on_completed, scheduler=scheduler
            )

        for idx in range(n):
            func(idx)
        return CompositeDisposable(subscriptions)

    return Observable(subscribe)
