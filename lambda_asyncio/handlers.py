from __future__ import annotations

import _thread
import asyncio.events
import asyncio.runners
import logging
import signal
import sys
from asyncio.unix_events import SelectorEventLoop
from collections import defaultdict
from contextlib import asynccontextmanager
from contextlib import AsyncExitStack
from functools import wraps
from threading import Thread
from typing import Any
from typing import AsyncContextManager
from typing import Awaitable
from typing import Callable
from typing import cast
from typing import List
from typing import MutableMapping
from typing import Optional
from typing import overload
from typing import TypeVar
from typing import Union

from typing_extensions import Protocol


T = TypeVar("T")
Response = TypeVar("Response")
InitCallback = Union[
    Callable[[], AsyncContextManager[Any]],
    Callable[[], Awaitable[Any]],
]

_loop: Optional[EventLoop] = None
_init_callbacks: MutableMapping[int, List[InitCallback]] = defaultdict(list)
_log = logging.getLogger(__name__)


def wrap_sig_handler(f, *fargs, **fkwargs):
    @wraps(f)
    def handler(*_):
        return f(*fargs, **fkwargs)

    return handler


class EventLoop(SelectorEventLoop):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.__term_event = self.create_future()
        self.__exit_stack = AsyncExitStack()

    @classmethod
    def run_in_background_thread(cls, *args, **kwargs) -> "EventLoop":
        loop = cls(*args, **kwargs)

        # We can't use loop.add_signal_handler because it schedules the callback
        # in the loop itself. It will run in the background thread, which then
        # can't make any other signal changes, and hence can't remove the signal
        # handlers

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, wrap_sig_handler(loop.__terminate, sig))

        # We are threading a bit dangerously into internals here
        csock = loop._csock  # type: ignore
        if csock:
            signal.set_wakeup_fd(csock.fileno())

        t = Thread(target=loop.__thread)
        t.start()

        return loop

    def __thread(self) -> None:
        asyncio.set_event_loop(self)

        try:
            try:
                self.run_until_complete(self.__term_event)
            except Exception:
                _log.exception('Completed with exception')
                sys.exit(1)
            finally:
                try:
                    _log.debug('Cancelling all tasks')
                    asyncio.runners._cancel_all_tasks(self)  # type: ignore

                    _log.debug('Shutting down asyncgens')
                    self.run_until_complete(self.shutdown_asyncgens())

                    if sys.version_info >= (3, 9):
                        _log.debug('Shutting down executors')
                        self.run_until_complete(self.shutdown_default_executor())

                    _log.debug('Shut down')
                    self.close()

                    asyncio.events.set_event_loop(None)
                except Exception:
                    sys.exit(1)
        finally:
            _thread.interrupt_main()

    async def __aterminate(self) -> None:
        _log.debug('Waiting for cleanup')
        try:
            await self.__exit_stack.aclose()
        except Exception:
            _log.exception("Failure cleaning up async inits")
        finally:
            self.__term_event.set_result(None)

    def __terminate(self, sig: signal.Signals) -> None:
        _log.warning(f'Got signal {sig}')

        if not self.__term_event.done():
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, signal.SIG_DFL)

            signal.set_wakeup_fd(-1)
            asyncio.run_coroutine_threadsafe(self.__aterminate(), loop=self)

    @overload
    async def with_resource(self, cm: Callable[[], Awaitable[T]]) -> T:
        pass

    @overload
    async def with_resource(self, cm: Callable[[], AsyncContextManager[T]]) -> T:
        pass

    async def with_resource(self, cm: InitCallback):
        coro = cm()
        if hasattr(coro, '__aexit__'):
            coro = cast(AsyncContextManager[Any], coro)
            value = await self.__exit_stack.enter_async_context(coro)
        else:
            # Define a dummy context manager to keep the resource alive
            @asynccontextmanager
            async def resource():
                yield (await coro)

            value = await self.__exit_stack.enter_async_context(resource())

        return value


async def run_init_callbacks(loop: EventLoop) -> None:
    for _, callbacks in sorted(_init_callbacks.items()):
        for callback in callbacks:
            await loop.with_resource(callback)


def get_loop() -> EventLoop:
    # Can't use the standard _get_running_loop() since this loop belongs to a different
    # thread
    global _loop
    if _loop is not None:
        return _loop

    _loop = EventLoop.run_in_background_thread()
    f = asyncio.run_coroutine_threadsafe(run_init_callbacks(_loop), loop=_loop)
    f.result()

    return _loop


LambdaAsyncHandler = Callable[..., Awaitable[Response]]
LambdaHandler = Callable[..., Response]


class LambdaAsyncHandlerDecorator(Protocol):
    def __call__(self, f: LambdaAsyncHandler) -> LambdaHandler:
        pass


def lambda_async_handler(*, eager: bool = True) -> LambdaAsyncHandlerDecorator:
    def decorate(f: LambdaAsyncHandler) -> LambdaHandler:
        @wraps(f)
        def handler(*args, **kwargs) -> Response:
            loop = get_loop()

            fut = asyncio.run_coroutine_threadsafe(f(*args, **kwargs), loop=loop)
            return fut.result()

        if eager:
            get_loop()

        return handler

    return decorate


class LambdaAsyncInitDecorator(Protocol):
    @overload
    def __call__(
        self, cm: Callable[[], AsyncContextManager[T]],
    ) -> Callable[[], Awaitable[T]]:
        pass

    @overload
    def __call__(
        self, f: Callable[[], Awaitable[T]],
    ) -> Callable[[], Awaitable[T]]:
        pass


def lambda_async_init(*, order: Optional[int] = None) -> LambdaAsyncInitDecorator:
    def decorate(cm):
        if order:
            global _init_callbacks
            _init_callbacks[order].append(cm)

        async def wrapper(*args, **kwargs):
            if hasattr(wrapper, '__return_value'):
                return wrapper.__return_value

            loop = get_loop()
            return_value = await loop.with_resource(cm)
            wrapper.__return_value = return_value

            return return_value

        return wrapper

    return decorate
